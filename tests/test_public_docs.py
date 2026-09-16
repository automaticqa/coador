from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from coador.model import SCHEMA_VERSION
from coador.scanner import scan


def test_public_markdown_links_resolve() -> None:
    documents = [
        *Path("docs").rglob("*.md"),
        *Path("examples").rglob("*.md"),
        *(
            Path(name)
            for name in (
                "README.md",
                "ARCHITECTURE.md",
                "CONTRIBUTING.md",
                "SECURITY.md",
                "CHANGELOG.md",
            )
        ),
    ]
    for document in documents:
        content = document.read_text(encoding="utf-8")
        for link in re.findall(r"\[[^\]]*\]\(([^\s)]+)\)", content):
            target = urlsplit(link)
            if target.scheme or target.netloc:
                continue
            path = document.parent / unquote(target.path) if target.path else document
            assert path.exists(), (document, link)


def test_local_example_uses_current_schema_and_source_evidence() -> None:
    profile = scan(Path("tests/fixtures/mini_android"))
    assert profile.schema_version == SCHEMA_VERSION == 3
    runner = profile.find_section("07_testing", "instrumentation_runner")
    assert runner is not None
    assert "com.example.mini.HiltTestRunner" in str(runner.items) + runner.summary
    assert runner.evidence
    assert all(not Path(item.path).is_absolute() for item in runner.evidence)
