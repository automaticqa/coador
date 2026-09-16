from __future__ import annotations

import json
from pathlib import Path

import pytest

from coador.cli import _format_section, emit, main
from coador.model import Section


def test_scan_then_status_reports_fresh(
    repo_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["scan", str(repo_copy)]) == 0
    capsys.readouterr()

    assert main(["status", str(repo_copy)]) == 0
    assert "up to date" in capsys.readouterr().out


def test_status_without_a_knowledge_base_fails(
    repo_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["status", str(repo_copy)]) == 1
    assert "No knowledge base found" in capsys.readouterr().out


def test_status_json_carries_state_and_paths(
    repo_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["scan", str(repo_copy)])
    capsys.readouterr()

    main(["status", str(repo_copy), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "fresh"
    assert payload["repo_path"] == str(repo_copy)
    assert payload["files_count"] > 0
    assert payload["scan_mode"] == "heuristic"
    assert payload["requested_scan_mode"] == "heuristic"
    assert payload["gradle_fallback"] is False
    assert payload["evidence_limit"] == 25


def test_layers_lists_all_nine(repo_copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["scan", str(repo_copy)])
    capsys.readouterr()

    assert main(["layers", str(repo_copy), "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 9


def test_show_renders_a_section(repo_copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["scan", str(repo_copy)])
    capsys.readouterr()

    assert main(["show", "03_architecture", "di_framework", str(repo_copy)]) == 0
    out = capsys.readouterr().out
    assert "DI Framework" in out
    assert "Hilt" in out


def test_show_pages_inventory_items_deterministically(
    repo_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["scan", str(repo_copy)])
    capsys.readouterr()

    command = [
        "show",
        "08_ui_testing",
        "test_tag_inventory",
        str(repo_copy),
        "--limit",
        "1",
        "--json",
    ]
    assert main(command) == 0
    first = json.loads(capsys.readouterr().out)
    assert len(first["items"]) == 1
    assert first["pagination"] == {
        "offset": 0,
        "limit": 1,
        "returned": 1,
        "total": 3,
        "next_cursor": "1",
    }

    assert main([*command[:-1], "--cursor", "1", "--json"]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["items"] != first["items"]
    assert second["pagination"]["offset"] == 1


def test_show_rejects_invalid_inventory_cursor(
    repo_copy: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    main(["scan", str(repo_copy)])
    capsys.readouterr()

    assert (
        main(
            [
                "show",
                "08_ui_testing",
                "test_tag_inventory",
                str(repo_copy),
                "--cursor",
                "invalid",
            ]
        )
        == 1
    )
    assert "Invalid inventory cursor" in caplog.text


def test_show_reports_unknown_section(repo_copy: Path) -> None:
    main(["scan", str(repo_copy)])
    assert main(["show", "03_architecture", "nope", str(repo_copy)]) == 1


def test_scan_outside_a_gradle_project_fails(tmp_path: Path) -> None:
    assert main(["scan", str(tmp_path)]) == 1


def test_repository_root_cannot_be_selected_as_kb_directory(repo_copy: Path) -> None:
    assert main(["scan", str(repo_copy), "--kb-dir", str(repo_copy)]) == 1


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "usage: coador" in capsys.readouterr().err


def test_overview_summarises_the_project(
    repo_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["scan", str(repo_copy)])
    capsys.readouterr()

    assert main(["overview", str(repo_copy), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["project"] == "mini-android"
    assert payload["highlights"]["di"] == "Hilt"
    assert len(payload["layers"]) == 9


def test_search_ranks_sections(repo_copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["scan", str(repo_copy)])
    capsys.readouterr()

    assert main(["search", "retrofit", str(repo_copy), "--json"]) == 0
    hits = json.loads(capsys.readouterr().out)
    assert hits[0]["section"] == "networking_stack"


def test_search_without_matches_reports_it(
    repo_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["scan", str(repo_copy)])
    capsys.readouterr()

    assert main(["search", "zzzz-not-a-real-term", str(repo_copy)]) == 1
    assert "Nothing matched" in capsys.readouterr().out


def test_search_can_be_limited_to_a_layer(
    repo_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["scan", str(repo_copy)])
    capsys.readouterr()

    main(["search", "test", str(repo_copy), "--layer", "09_ci_cd", "--json"])
    hits = json.loads(capsys.readouterr().out)
    assert hits and {hit["layer"] for hit in hits} == {"09_ci_cd"}


def test_commands_need_a_knowledge_base(repo_copy: Path) -> None:
    assert main(["overview", str(repo_copy)]) == 1
    assert main(["search", "hilt", str(repo_copy)]) == 1


def test_text_and_json_output_sanitize_mutated_model_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    section = Section(id="navigation", title="Navigation", detected=True, summary="safe")
    section.summary = 'token = "CANARY"'
    emit(section.to_dict(), True, _format_section(section))
    assert "CANARY" not in capsys.readouterr().out


@pytest.mark.parametrize("external", [False, True])
def test_cli_lifecycle_preserves_android_sources_and_legacy_bases(
    repo_copy: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], external: bool
) -> None:
    (repo_copy / ".gitignore").write_text("# User-owned rules\nbuild/\n", encoding="utf-8")
    legacy = repo_copy / ".existing-notes"
    legacy.mkdir()
    (legacy / "notes.md").write_text("User-owned legacy notes\n", encoding="utf-8")

    def source_snapshot() -> dict[str, tuple[bytes, int, int]]:
        return {
            path.relative_to(repo_copy).as_posix(): (
                path.read_bytes(),
                path.stat().st_mtime_ns,
                path.stat().st_mode,
            )
            for path in repo_copy.rglob("*")
            if path.is_file() and ".coador" not in path.relative_to(repo_copy).parts
        }

    before = source_snapshot()
    kb_dir = tmp_path / "external knowledge base" if external else repo_copy / ".coador"
    location = [str(repo_copy)]
    if external:
        location += ["--kb-dir", str(kb_dir)]
    for command in (
        ["scan"],
        ["scan", "--force"],
        ["status", "--verify-content"],
        ["layers"],
        ["overview"],
        ["search", "retrofit"],
        ["show", "03_architecture", "di_framework"],
    ):
        assert main([*command, *location, "--json"]) == 0
        json.loads(capsys.readouterr().out)
        assert source_snapshot() == before

    assert (kb_dir / "profile.json").is_file()
    if external:
        assert not (repo_copy / ".coador").exists()
