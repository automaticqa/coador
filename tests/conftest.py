from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from coador.kb import KnowledgeBase
from coador.model import Profile
from coador.scanner import scan

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "mini_android"


@pytest.fixture(scope="session")
def fixture_repo() -> Path:
    """The synthetic Android project every test scans."""
    return FIXTURE_REPO


@pytest.fixture(scope="session")
def fixture_profile() -> Profile:
    """One scan of the fixture, shared by the tests that only read it."""
    return scan(FIXTURE_REPO)


@pytest.fixture
def repo_copy(tmp_path: Path) -> Path:
    """A writable copy of the fixture, for tests that modify files."""
    target = tmp_path / "mini_android"
    shutil.copytree(FIXTURE_REPO, target, ignore=shutil.ignore_patterns(".coador"))
    return target


@pytest.fixture
def kb(repo_copy: Path) -> KnowledgeBase:
    return KnowledgeBase.for_repo(repo_copy)
