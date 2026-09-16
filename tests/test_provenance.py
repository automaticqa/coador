from __future__ import annotations

from pathlib import Path

import pytest

from coador.detectors.base import Evidence as DetectorEvidence
from coador.fileindex import active_index, get_index
from coador.model import Evidence, Profile, Provenance, SchemaMismatchError
from coador.textscan import grep_files


def test_exact_provenance_has_real_snapshot_bounds() -> None:
    evidence = Evidence.from_source("app/Main.kt", "first\nsecond\nthird\n", 2, 3)
    assert evidence.snippet == "second\nthird"
    assert evidence.source_line_count == 3
    assert Evidence.from_dict(evidence.to_dict()) == evidence


@pytest.mark.parametrize("start,end", [(0, 1), (2, 1), (1, 4), (-1, 1), (True, 1)])
def test_invalid_ranges_are_rejected(start: int, end: int) -> None:
    with pytest.raises(ValueError):
        Evidence.from_source("Main.kt", "one\ntwo\nthree", start, end)


def test_file_and_model_facts_have_no_lines() -> None:
    for evidence in [
        Evidence(
            path="app", provenance=Provenance.FILE, entry_type="directory", snippet="Test sources"
        ),
        Evidence(
            provenance=Provenance.GRADLE_MODEL,
            project=":app",
            property="android.buildTypes",
            snippet="debug",
        ),
    ]:
        data = evidence.to_dict()
        assert "line_start" not in data and "line_end" not in data
        assert Evidence.from_dict(data) == evidence


@pytest.mark.parametrize("version", [None, 1, 2, 4, "3", True])
def test_old_or_unknown_profiles_are_not_upgraded(version: object) -> None:
    with pytest.raises(SchemaMismatchError):
        Profile.from_dict({"schema_version": version, "layers": []})


def test_exact_evidence_uses_captured_content_after_file_changes(tmp_path: Path) -> None:
    path = tmp_path / "Main.kt"
    path.write_text("before\nmatch\nend", encoding="utf-8")
    matches = grep_files(tmp_path, "match", "*.kt")
    path.write_text("changed", encoding="utf-8")
    token = active_index.set(get_index(tmp_path))
    try:
        ev = DetectorEvidence.from_match("Main.kt", 2, matches[0].line_content)
    finally:
        active_index.reset(token)
    assert ev.exact is not None and ev.exact.snippet == "match"
    assert ev.exact.source_line_count == 3


def test_multiline_evidence_captures_complete_match(tmp_path: Path) -> None:
    (tmp_path / "ci.yml").write_text(
        "artifacts:\n  reports:\n    junit: report.xml\n", encoding="utf-8"
    )
    matches = grep_files(tmp_path, r"artifacts:\s+reports:", "*.yml", multiline=True)
    token = active_index.set(get_index(tmp_path))
    try:
        ev = DetectorEvidence.from_match("ci.yml", matches[0].line_number, matches[0].line_content)
    finally:
        active_index.reset(token)
    assert ev.exact is not None and ev.exact.line_end == 2


def test_self_asserted_exact_provenance_cannot_bypass_scan_validation(tmp_path: Path) -> None:
    from coador.scanner import _to_model_evidence

    (tmp_path / "Main.kt").write_text("actual content")
    fake = Evidence.from_source("Main.kt", "fabricated content", 1)
    pending = DetectorEvidence("Main.kt", 1, 1, "fabricated content", Provenance.SOURCE_LINES, fake)
    with pytest.raises(ValueError, match="Unverified"):
        _to_model_evidence(pending, tmp_path)
