from __future__ import annotations

import tomllib
from pathlib import Path


def test_feedback_never_requires_private_project_material() -> None:
    form = Path(".github/ISSUE_TEMPLATE/usage_feedback.yml").read_text(encoding="utf-8")

    required_general_fields = ("stage", "interface", "outcome")
    for field_id in required_general_fields:
        block = form.split(f"    id: {field_id}\n", 1)[1].split("  - type:", 1)[0]
        assert "required: true" in block

    optional_context = form.split("    id: public_context\n", 1)[1].split("  - type:", 1)[0]
    assert "required: true" not in optional_context
    assert "repository name, source code, generated" in form
    assert "type: upload" not in form


def test_feedback_policy_preserves_privacy_boundaries() -> None:
    policy = Path("docs/adoption.md").read_text(encoding="utf-8")
    normalized = " ".join(policy.split()).casefold()

    assert "no telemetry" in normalized
    assert "participation is voluntary" in normalized
    assert "synthetic reproduction" in normalized
    assert "remove credentials, personal information and private-project details" in normalized
    assert "[security.md](../security.md)" in normalized


def test_runtime_dependencies_do_not_add_an_analytics_sdk() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert project["dependencies"] == ["mcp>=2.2,<3"]


def test_public_documents_share_the_no_telemetry_boundary() -> None:
    documents = (
        "README.md",
        "SECURITY.md",
        "docs/adoption.md",
        "docs/releases/0.1.0.md",
    )
    for path in documents:
        content = Path(path).read_text(encoding="utf-8").casefold()
        assert "telemetry" in content, path
