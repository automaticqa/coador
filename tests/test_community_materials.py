from __future__ import annotations

import re
from pathlib import Path

ISSUE_TEMPLATE_DIR = Path(".github/ISSUE_TEMPLATE")
FORM_NAMES = ("bug_report.yml", "detector_gap.yml", "documentation.yml", "usage_feedback.yml")


def _form_text(name: str) -> str:
    return (ISSUE_TEMPLATE_DIR / name).read_text(encoding="utf-8")


def test_issue_forms_have_required_structure_and_unique_ids() -> None:
    for name in FORM_NAMES:
        form = _form_text(name)
        assert form.startswith("name: ")
        assert "\ndescription: " in form
        assert "\nbody:\n" in form
        assert "\n    id: " in form
        ids = re.findall(r"^    id: ([a-z0-9_-]+)$", form, flags=re.MULTILINE)
        assert len(ids) == len(set(ids))
        assert "labels:" not in form
        assert "assignees:" not in form
        assert "projects:" not in form


def test_issue_forms_request_actionable_sanitized_reports() -> None:
    bug = _form_text("bug_report.yml")
    for field_id in ("version", "interface", "scan_mode", "target_shape", "steps"):
        assert f"    id: {field_id}\n" in bug
    assert "follow SECURITY.md instead" in bug
    assert "I removed secrets, private source, internal URLs, and personal data" in bug

    detector = _form_text("detector_gap.yml")
    for field_id in ("question", "layer", "current_output", "evidence", "expected_boundary"):
        assert f"    id: {field_id}\n" in detector
    assert "positive evidence, a negative case" in detector

    feedback = _form_text("usage_feedback.yml")
    for field_id in ("stage", "interface", "outcome", "elapsed", "public_context"):
        assert f"    id: {field_id}\n" in feedback
    assert "This public feedback is voluntary" in feedback
    assert "A repository name" in feedback
    assert "type: upload" not in feedback

    config = _form_text("config.yml")
    assert config == "blank_issues_enabled: false\n"


def test_starter_tasks_are_bounded_and_discoverable() -> None:
    tasks = Path("docs/contributor-tasks.md").read_text(encoding="utf-8")
    contributing = Path("CONTRIBUTING.md").read_text(encoding="utf-8")

    assert tasks.count("## ") == 4
    assert tasks.count("**Outcome:**") == 3
    assert tasks.count("**Likely files:**") == 3
    assert tasks.count("**Acceptance:**") == 3
    assert tasks.count("**Not in scope:**") == 3
    assert "[starter contribution tasks](docs/contributor-tasks.md)" in contributing
    assert "SECURITY.md" in contributing


def test_release_notes_link_to_public_guides_and_record_release_date() -> None:
    release = Path("docs/releases/0.1.0.md").read_text(encoding="utf-8")

    for target in (
        "../../README.md#installation",
        "../../examples/README.md",
        "../onboarding-recipes.md",
        "../contributor-tasks.md",
        "../mcp.md",
        "../../SECURITY.md",
    ):
        assert target in release

    assert release.startswith("# Coador 0.1.0\n\nRelease date: 2026-09-17.")
