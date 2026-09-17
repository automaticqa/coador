"""Exercise the installed ``coador-mcp`` entry point over real stdio."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, TextIO, cast

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EXPECTED_TOOLS = {
    "kb_get_section",
    "kb_list_layers",
    "kb_overview",
    "kb_refresh",
    "kb_search",
    "kb_status",
}
SESSION_TIMEOUT_SECONDS = 45


def _entry_point() -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    entry_point = Path(sys.executable).with_name(f"coador-mcp{suffix}")
    if not entry_point.is_file():
        raise AssertionError(f"Installed MCP entry point is missing: {entry_point}")
    return entry_point


def _structured(result: Any) -> dict[str, Any]:
    if result.is_error:
        raise AssertionError(f"MCP tool failed: {result.content}")
    if not isinstance(result.structured_content, dict):
        raise AssertionError(f"MCP tool returned no structured object: {result.content}")
    return cast(dict[str, Any], result.structured_content)


async def _exercise_server(source_fixture: Path, errlog: TextIO, via_cli: bool = False) -> None:
    protocol_errors: list[Exception] = []

    async def record_protocol_error(message: Any) -> None:
        if isinstance(message, Exception):
            protocol_errors.append(message)

    with tempfile.TemporaryDirectory(prefix="coador-stdio-") as raw_temp:
        temp_root = Path(raw_temp)
        repo = temp_root / "Android project with spaces"
        kb_dir = temp_root / "external knowledge base"
        launch_dir = temp_root / "unrelated launch directory"
        shutil.copytree(source_fixture, repo)
        launch_dir.mkdir()
        (repo / ".gitignore").write_text("# User-owned rules\nbuild/\n", encoding="utf-8")
        source_before = {
            path.relative_to(repo): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in repo.rglob("*")
            if path.is_file()
        }

        parameters = StdioServerParameters(
            command=str(
                _entry_point().with_name("coador.exe" if sys.platform == "win32" else "coador")
                if via_cli
                else _entry_point()
            ),
            args=(["mcp"] if via_cli else []) + ["--repo", str(repo), "--kb-dir", str(kb_dir)],
            cwd=launch_dir,
        )

        with anyio.fail_after(SESSION_TIMEOUT_SECONDS):
            async with (
                stdio_client(parameters, errlog=errlog) as streams,
                ClientSession(*streams, message_handler=record_protocol_error) as session,
            ):
                initialized = await session.initialize()
                assert initialized.server_info.name == "coador"
                assert initialized.instructions is not None
                assert "Start with `kb_overview`" in initialized.instructions

                listed = await session.list_tools()
                tools = {tool.name: tool for tool in listed.tools}
                assert set(tools) == EXPECTED_TOOLS
                assert tools["kb_refresh"].annotations is not None
                assert tools["kb_refresh"].annotations.read_only_hint is False
                for name in EXPECTED_TOOLS - {"kb_refresh"}:
                    assert tools[name].annotations is not None
                    assert tools[name].annotations.read_only_hint is True

                missing = _structured(await session.call_tool("kb_status"))
                assert missing["state"] == "missing"
                reported_repo = Path(missing["repository"])
                assert reported_repo.is_absolute()
                assert reported_repo.samefile(repo)

                unavailable = await session.call_tool("kb_overview")
                assert unavailable.is_error
                assert "kb_refresh" in str(unavailable.content)

                refreshed = _structured(await session.call_tool("kb_refresh"))
                assert refreshed["action"] == "scanned"
                assert refreshed["state"] == "fresh"
                assert kb_dir.joinpath("profile.json").is_file()

                overview = _structured(await session.call_tool("kb_overview"))
                assert overview["project"] == "mini-android"

                layers = _structured(await session.call_tool("kb_list_layers"))
                assert len(layers["result"]) == 9
                resources = await session.list_resources()
                assert "kb://layers" in {str(resource.uri) for resource in resources.resources}
                for uri in (
                    "kb://layers",
                    "kb://layer/03_architecture",
                    "kb://section/03_architecture/di_framework",
                ):
                    resource = await session.read_resource(uri)
                    assert resource.contents
                    content = resource.contents[0]
                    assert hasattr(content, "text")
                    assert json.loads(content.text)

                section = _structured(
                    await session.call_tool(
                        "kb_get_section",
                        {"layer_id": "03_architecture", "section_id": "di_framework"},
                    )
                )
                assert section["summary"] == "Hilt"
                assert section["evidence"]

                search = _structured(
                    await session.call_tool("kb_search", {"query": "retrofit", "limit": 3})
                )
                assert search["result"][0]["section"] == "networking_stack"

                invalid = await session.call_tool(
                    "kb_get_section",
                    {"layer_id": "03_architecture", "section_id": "not-a-section"},
                )
                assert invalid.is_error
                assert "Unknown section" in str(invalid.content)

        assert {
            path.relative_to(repo): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in repo.rglob("*")
            if path.is_file()
        } == source_before

    assert not protocol_errors, f"Non-protocol stdout received: {protocol_errors}"


def _run_smoke(source_fixture: Path) -> str:
    if not source_fixture.is_dir():
        raise AssertionError(f"fixture directory does not exist: {source_fixture}")

    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errlog:
        try:
            anyio.run(_exercise_server, source_fixture, errlog, False)
            anyio.run(_exercise_server, source_fixture, errlog, True)
        finally:
            errlog.seek(0)
            diagnostics = errlog.read()
            if sys.exc_info()[0] is not None:
                print(diagnostics, file=sys.stderr)

    assert "Serving" in diagnostics
    assert "Traceback" not in diagnostics
    return diagnostics


def test_installed_entry_point_over_stdio(fixture_repo: Path) -> None:
    _run_smoke(fixture_repo)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_mcp_stdio.py PATH_TO_MINI_ANDROID_FIXTURE")

    source_fixture = Path(sys.argv[1]).resolve()
    _run_smoke(source_fixture)
    print("Installed-wheel MCP stdio lifecycle passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
