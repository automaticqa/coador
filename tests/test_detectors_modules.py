from pathlib import Path

import pytest

from coador.detectors.modules import FlavorOverridesDetector


@pytest.mark.parametrize("src_path", ["src", ".github/actions/example/src"])
@pytest.mark.parametrize("source_kind", ["java", "kotlin", "res"])
def test_flavor_overrides_skips_files_and_keeps_valid_siblings(
    tmp_path: Path, src_path: str, source_kind: str
) -> None:
    src = tmp_path / src_path
    (src / "demo" / source_kind).mkdir(parents=True)
    (src / "README.md").write_text("Source layout notes", encoding="utf-8")
    (src / "markdown.ts").write_text("export {};", encoding="utf-8")

    result = FlavorOverridesDetector(tmp_path).detect()

    assert result.error is None
    assert result.detected
    assert result.description == "1 flavor source sets: demo"
    assert [(entry.file_path, entry.snippet) for entry in result.evidence] == [
        (f"{src_path}/demo", "Flavor source set: demo")
    ]


@pytest.mark.parametrize("src_path", ["src", ".github/actions/example/src"])
def test_flavor_overrides_with_only_files_has_no_findings(tmp_path: Path, src_path: str) -> None:
    src = tmp_path / src_path
    src.mkdir(parents=True)
    (src / "markdown.ts").write_text("export {};", encoding="utf-8")

    result = FlavorOverridesDetector(tmp_path).detect()

    assert result.error is None
    assert not result.detected
    assert result.evidence == []


def test_flavor_overrides_preserves_standard_and_nested_custom_layouts(tmp_path: Path) -> None:
    for name in ("main", "test", "androidTest", "debug", "release"):
        (tmp_path / "app" / "src" / name / "java").mkdir(parents=True)
    expected = {"app/src/demo", "feature/login/src/paid", "custom/layout/src/enterprise"}
    for path, source_kind in zip(sorted(expected), ("java", "kotlin", "res"), strict=True):
        (tmp_path / path / source_kind).mkdir(parents=True)
    (tmp_path / "app/src/empty").mkdir()

    result = FlavorOverridesDetector(tmp_path).detect()

    assert result.error is None
    assert result.detected
    assert result.description == "3 flavor source sets: demo, enterprise, paid"
    assert {entry.file_path for entry in result.evidence} == expected
