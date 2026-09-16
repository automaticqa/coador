from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from coador import scanner
from coador.cli import main
from coador.detectors.base import BaseDetector, DetectionResult, Evidence
from coador.kb import KnowledgeBase
from coador.mcp_server import create_server
from coador.model import ResultKind
from coador.registry import DetectorSpec


class CanaryDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Canary detector"

    def detect(self) -> DetectionResult:
        return DetectionResult(
            True,
            'token="CANARY_SUMMARY"',
            [
                Evidence("settings.gradle.kts", 1, 1, 'password="CANARY_SNIPPET"'),
            ],
            items=['secret="CANARY_ITEM"'],
        )


class FailedDetector(CanaryDetector):
    def detect(self) -> DetectionResult:
        raise RuntimeError("CANARY_RAW_ERROR")


@pytest.fixture
def canary_kb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> KnowledgeBase:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "settings.gradle.kts").write_text('rootProject.name = "safe"\n')
    specs = (
        DetectorSpec(
            "repository_identity",
            "01_overview",
            "Identity",
            CanaryDetector,
            kind=ResultKind.INVENTORY,
        ),
        DetectorSpec("brands_flavors_presence", "01_overview", "Failure", FailedDetector),
    )
    monkeypatch.setattr(scanner, "DETECTORS", specs)
    return KnowledgeBase.for_repo(repo, tmp_path / "kb")


def test_canaries_do_not_reach_profile_markdown_cli_search_or_logs(
    canary_kb: KnowledgeBase, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    profile = scanner.scan(canary_kb.repo_root)
    assert "CANARY" not in json.dumps(profile.to_dict())
    failed = profile.find_section("01_overview", "brands_flavors_presence")
    assert failed is not None and failed.error == "Detector failed"
    canary_kb.refresh()
    for path in [canary_kb.profile_path, *canary_kb.layers_dir.glob("*.md")]:
        assert "CANARY" not in path.read_text(), path
    assert not canary_kb.search("CANARY_ITEM")
    for command in [
        ["overview"],
        ["layers"],
        ["status"],
        ["show", "01_overview", "repository_identity"],
        ["search", "secret"],
    ]:
        for output in [[], ["--json"]]:
            main([*command, str(canary_kb.repo_root), "--kb-dir", str(canary_kb.kb_dir), *output])
            captured = capsys.readouterr()
            assert "CANARY" not in captured.out + captured.err
    assert "CANARY" not in caplog.text


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_canaries_do_not_reach_mcp_tools_resources_or_logs(
    canary_kb: KnowledgeBase, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    server = create_server(canary_kb)
    for name, arguments in [
        ("kb_refresh", {}),
        ("kb_status", {}),
        ("kb_overview", {}),
        ("kb_list_layers", {}),
        ("kb_get_section", {"layer_id": "01_overview", "section_id": "repository_identity"}),
        ("kb_search", {"query": "secret"}),
    ]:
        result = await server.call_tool(name, arguments)
        assert not result.is_error
        assert "CANARY" not in str(result)
    for uri in [
        "kb://layers",
        "kb://layer/01_overview",
        "kb://section/01_overview/repository_identity",
    ]:
        result = await server.read_resource(uri)
        assert "CANARY" not in str(result)
    assert "CANARY" not in caplog.text


def test_forced_scans_are_identical_and_preserve_manual_header(canary_kb: KnowledgeBase) -> None:
    canary_kb.refresh(force=True)
    layer = canary_kb.layers_dir / "01_overview.md"
    layer.write_text("Manual token=USER_OWNED_HEADER\n" + layer.read_text())
    canary_kb.refresh(force=True)
    before = {
        p.name: p.read_bytes() for p in [canary_kb.profile_path, *canary_kb.layers_dir.glob("*.md")]
    }
    canary_kb.refresh(force=True)
    after = {
        p.name: p.read_bytes() for p in [canary_kb.profile_path, *canary_kb.layers_dir.glob("*.md")]
    }
    assert before == after
    assert "Manual token=USER_OWNED_HEADER" in layer.read_text()


def test_invalid_evidence_is_reported_without_a_fabricated_citation(tmp_path: Path) -> None:
    result = DetectionResult(True, "Signal", [Evidence("../outside.kt", 1, 1, "CANARY_INVALID")])
    spec = DetectorSpec("repository_identity", "01_overview", "Identity", CanaryDetector)
    section = scanner._build_section(spec, result, 25, tmp_path)
    assert not section.evidence and not section.detected
    assert section.error == "Omitted 1 invalid evidence entries"
    assert "CANARY" not in json.dumps(section.to_dict())


def test_actual_source_context_is_clean_before_extraction(repo_copy: Path, tmp_path: Path) -> None:
    source = repo_copy / "Source.kt"
    source.write_text(
        '@Composable fun Visible() { val password = "CANARY_SECRETVALUE894321" }\n'
        'val api_key = """CANARY_FIRST\nCANARY_SECOND"""\n'
        'val node = Modifier.testTag("https://user:CANARY_AUTH@example.test/path?token=CANARY_QUERY")\n'
        'val accessToken = "CANARY_LEFT" + "CANARY_RIGHT"\n'
        'val refreshToken = "CANARY_LEFT" + suffix() + "CANARY_RIGHT"\n'
        'val refreshToken = primary ?: "CANARY_FALLBACK"\n'
    )
    kb = KnowledgeBase.for_repo(repo_copy, tmp_path / "safe-output")
    kb.refresh(force=True)
    profile = kb.require_profile()
    tags = profile.find_section("08_ui_testing", "test_tag_inventory")
    assert tags is not None and any("example.test" in item for item in tags.items)
    for path in [kb.profile_path, *kb.layers_dir.glob("*.md")]:
        assert "CANARY_" not in path.read_text()
    assert not kb.search("secretvalue894321")
