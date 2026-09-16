from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from coador.kb import KnowledgeBase
from coador.mcp_server import ENV_KB_DIR, ENV_REPO, create_server, resolve_knowledge_base
from coador.model import Layer, Section

pytestmark = pytest.mark.anyio

EXPECTED_TOOLS = {
    "kb_status",
    "kb_overview",
    "kb_list_layers",
    "kb_get_section",
    "kb_search",
    "kb_refresh",
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def scanned_kb(kb: KnowledgeBase) -> KnowledgeBase:
    kb.refresh()
    return kb


def _structured(result: Any) -> Any:
    assert not result.is_error, result.content
    return result.structured_content


async def test_every_tool_is_exposed(scanned_kb: KnowledgeBase) -> None:
    tools = await create_server(scanned_kb).list_tools()
    assert {tool.name for tool in tools} == EXPECTED_TOOLS
    for tool in tools:
        assert tool.description, tool.name


async def test_only_refresh_is_allowed_to_write(scanned_kb: KnowledgeBase) -> None:
    tools = {tool.name: tool for tool in await create_server(scanned_kb).list_tools()}
    for name in EXPECTED_TOOLS - {"kb_refresh"}:
        assert tools[name].annotations is not None
        assert tools[name].annotations.read_only_hint is True, name
    assert tools["kb_refresh"].annotations.read_only_hint is False


async def test_resources_and_templates_are_published(scanned_kb: KnowledgeBase) -> None:
    server = create_server(scanned_kb)
    resources = {str(resource.uri) for resource in await server.list_resources()}
    templates = {template.uri_template for template in await server.list_resource_templates()}

    assert "kb://layers" in resources
    assert "kb://layer/{layer_id}" in templates
    assert "kb://section/{layer_id}/{section_id}" in templates


async def test_overview_answers_what_the_project_is(scanned_kb: KnowledgeBase) -> None:
    overview = _structured(await create_server(scanned_kb).call_tool("kb_overview", {}))
    assert overview["project"] == "mini-android"
    assert overview["highlights"]["di"] == "Hilt"


async def test_status_reports_a_fresh_knowledge_base(scanned_kb: KnowledgeBase) -> None:
    status = _structured(await create_server(scanned_kb).call_tool("kb_status", {}))
    assert status["state"] == "fresh"
    assert status["needs_refresh"] is False
    assert status["scan_mode"] == "heuristic"
    assert status["requested_scan_mode"] == "heuristic"
    assert status["gradle_fallback"] is False
    assert status["evidence_limit"] == 25


async def test_get_section_returns_evidence(scanned_kb: KnowledgeBase) -> None:
    section = _structured(
        await create_server(scanned_kb).call_tool(
            "kb_get_section", {"layer_id": "03_architecture", "section_id": "di_framework"}
        )
    )
    assert section["summary"] == "Hilt"
    assert section["layer"] == "03_architecture"
    assert section["evidence"], "a claim without evidence is not useful"


async def test_get_section_pages_inventory_with_continuation(
    scanned_kb: KnowledgeBase,
) -> None:
    server = create_server(scanned_kb)
    first = _structured(
        await server.call_tool(
            "kb_get_section",
            {"layer_id": "08_ui_testing", "section_id": "test_tag_inventory", "limit": 1},
        )
    )
    assert len(first["items"]) == 1
    assert first["pagination"]["total"] == 3
    assert first["pagination"]["next_cursor"] == "1"

    second = _structured(
        await server.call_tool(
            "kb_get_section",
            {
                "layer_id": "08_ui_testing",
                "section_id": "test_tag_inventory",
                "limit": 1,
                "cursor": first["pagination"]["next_cursor"],
            },
        )
    )
    assert second["pagination"]["offset"] == 1
    assert second["items"] != first["items"]


async def test_get_section_rejects_invalid_inventory_cursor(
    scanned_kb: KnowledgeBase,
) -> None:
    with pytest.raises(ToolError, match="Invalid inventory cursor"):
        await create_server(scanned_kb).call_tool(
            "kb_get_section",
            {
                "layer_id": "08_ui_testing",
                "section_id": "test_tag_inventory",
                "cursor": "invalid",
            },
        )


async def test_unknown_ids_explain_what_is_available(scanned_kb: KnowledgeBase) -> None:
    server = create_server(scanned_kb)

    with pytest.raises(ToolError, match="Unknown layer"):
        await server.call_tool("kb_get_section", {"layer_id": "nope", "section_id": "x"})

    with pytest.raises(ToolError, match="Unknown section"):
        await server.call_tool(
            "kb_get_section", {"layer_id": "03_architecture", "section_id": "nope"}
        )


async def test_search_returns_ranked_hits(scanned_kb: KnowledgeBase) -> None:
    hits = _structured(
        await create_server(scanned_kb).call_tool("kb_search", {"query": "retrofit", "limit": 3})
    )
    assert hits["result"][0]["section"] == "networking_stack"


async def test_search_limit_is_clamped(scanned_kb: KnowledgeBase) -> None:
    hits = _structured(
        await create_server(scanned_kb).call_tool("kb_search", {"query": "test", "limit": 9999})
    )
    assert len(hits["result"]) <= 50


async def test_refresh_is_a_no_op_when_nothing_changed(scanned_kb: KnowledgeBase) -> None:
    result = _structured(await create_server(scanned_kb).call_tool("kb_refresh", {}))
    assert result["rescanned"] is False
    assert result["action"] == "no_op"
    assert result["state"] == "fresh"


async def test_refresh_builds_a_missing_knowledge_base(kb: KnowledgeBase) -> None:
    assert kb.status().state.value == "missing"

    result = _structured(await create_server(kb).call_tool("kb_refresh", {}))
    assert result["rescanned"] is True
    assert result["action"] == "scanned"
    assert result["state"] == "fresh"
    assert kb.profile_path.exists()


async def test_reading_before_a_scan_tells_the_agent_what_to_do(kb: KnowledgeBase) -> None:
    with pytest.raises(ToolError, match="kb_refresh"):
        await create_server(kb).call_tool("kb_overview", {})


async def test_layer_resource_is_readable(scanned_kb: KnowledgeBase) -> None:
    contents = list(await create_server(scanned_kb).read_resource("kb://layer/03_architecture"))
    assert contents
    assert "di_framework" in str(contents[0].content)


async def test_inventory_section_resource_returns_a_page(scanned_kb: KnowledgeBase) -> None:
    contents = list(
        await create_server(scanned_kb).read_resource(
            "kb://section/08_ui_testing/test_tag_inventory"
        )
    )
    assert contents
    assert "pagination" in str(contents[0].content)


async def test_tool_output_sanitizes_mutated_model_fields(
    scanned_kb: KnowledgeBase, monkeypatch: pytest.MonkeyPatch
) -> None:
    section = Section(id="navigation", title="Navigation", detected=True, summary="safe")
    section.summary = 'token = "CANARY"'
    layer = Layer(id="03_architecture", title="Architecture", sections=[section])
    monkeypatch.setattr(scanned_kb, "get_layer", lambda _layer_id: layer)
    result = await create_server(scanned_kb).call_tool(
        "kb_get_section", {"layer_id": "03_architecture", "section_id": "navigation"}
    )
    assert "CANARY" not in str(_structured(result))


def test_repository_is_resolved_from_arguments(repo_copy: Path) -> None:
    kb = resolve_knowledge_base(str(repo_copy), None)
    assert kb.repo_root == repo_copy
    assert kb.kb_dir == repo_copy / ".coador"


def test_repository_is_resolved_from_the_environment(
    repo_copy: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    external = tmp_path / "kb"
    assert ENV_REPO == "COADOR_REPO"
    assert ENV_KB_DIR == "COADOR_KB_DIR"
    monkeypatch.setenv(ENV_REPO, str(repo_copy))
    monkeypatch.setenv(ENV_KB_DIR, str(external))

    kb = resolve_knowledge_base(None, None)
    assert kb.repo_root == repo_copy
    assert kb.kb_dir == external


def test_a_directory_without_gradle_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="No Gradle project"):
        resolve_knowledge_base(str(tmp_path), None)


def test_repository_root_cannot_be_selected_as_kb_directory(repo_copy: Path) -> None:
    with pytest.raises(SystemExit, match="Invalid knowledge-base directory"):
        resolve_knowledge_base(str(repo_copy), str(repo_copy))
