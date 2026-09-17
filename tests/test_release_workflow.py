from __future__ import annotations

from pathlib import Path


def test_publish_workflow_requires_an_explicit_release() -> None:
    workflow = Path(".github/workflows/publish.yml").read_text(encoding="utf-8")

    assert "release:" in workflow
    assert "types: [published]" in workflow
    assert "push:" not in workflow
    assert "workflow_dispatch:" not in workflow


def test_publish_workflow_uses_least_privilege_oidc() -> None:
    workflow = Path(".github/workflows/publish.yml").read_text(encoding="utf-8")

    assert "contents: read" in workflow
    assert "environment:\n      name: pypi" in workflow
    assert "id-token: write" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "PYPI_TOKEN" not in workflow
    assert "password:" not in workflow


def test_publish_workflow_verifies_built_and_downloaded_artifacts() -> None:
    workflow = Path(".github/workflows/publish.yml").read_text(encoding="utf-8")

    assert workflow.count("tests/packaging/verify_release.py") == 2
    assert workflow.count('--expected-tag "$RELEASE_TAG"') == 2
    assert workflow.index("verify downloaded archives again") < workflow.index(
        "publish with PyPI trusted publishing"
    )


def test_publish_workflow_repeats_release_gates_before_building() -> None:
    workflow = Path(".github/workflows/publish.yml").read_text(encoding="utf-8")

    gates = (
        "uv run pytest",
        "uv run ruff check src tests",
        "uv run ruff format --check src tests",
        "uv run mypy",
        "uv run python -m coador.registry --check",
    )
    build_position = workflow.index("uv build")
    for gate in gates:
        assert workflow.index(gate) < build_position
    assert "install and exercise the release wheel" in workflow
    assert "tests/test_mcp_stdio.py" in workflow


def test_registry_publication_follows_pypi_and_validates_metadata() -> None:
    workflow = Path(".github/workflows/publish.yml").read_text(encoding="utf-8")
    registry_job = workflow.split("  publish-registry:", 1)[1]
    assert "needs: publish" in registry_job
    assert "id-token: write" in registry_job
    assert "./mcp-publisher login github-oidc" in registry_job
    assert registry_job.index("validate server.json") < registry_job.index("publish server.json")
    assert registry_job.index("wait for the PyPI release") < registry_job.index(
        "publish server.json"
    )
