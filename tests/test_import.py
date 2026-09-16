from __future__ import annotations

import re

import coador
from coador import cli


def test_version_is_pep440_like() -> None:
    assert re.match(r"^\d+\.\d+\.\d+", coador.__version__)


def test_cli_version_flag(capsys) -> None:  # type: ignore[no-untyped-def]
    try:
        cli.main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    out = capsys.readouterr().out
    assert coador.__version__ in out
