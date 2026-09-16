from __future__ import annotations

from pathlib import Path

import pytest

from coador.fileindex import invalidate
from coador.model import InventoryCompleteness, Profile, Provenance, ResultKind


@pytest.fixture(autouse=True)
def _fresh_index() -> None:
    invalidate()


def test_instrumentation_runner_names_the_runner_and_application(fixture_profile: Profile) -> None:
    section = fixture_profile.find_section("07_testing", "instrumentation_runner")
    assert section is not None and section.detected
    assert "com.example.mini.HiltTestRunner" in section.summary
    assert "custom runner class" in section.summary
    assert "test Application override" in section.summary


def test_test_tasks_reports_the_gradle_task_used_by_ci(fixture_profile: Profile) -> None:
    section = fixture_profile.find_section("07_testing", "test_tasks")
    assert section is not None and section.detected
    assert "testDemoDebugUnitTest" in section.summary


def test_dependency_substitution_lists_the_mechanisms(fixture_profile: Profile) -> None:
    section = fixture_profile.find_section("07_testing", "test_dependency_substitution")
    assert section is not None and section.detected
    for mechanism in ("Hilt test modules", "MockWebServer", "Fake implementations"):
        assert mechanism in section.summary


def test_entry_points_point_at_rules_and_helpers(fixture_profile: Profile) -> None:
    section = fixture_profile.find_section("07_testing", "test_entry_points")
    assert section is not None and section.detected
    assert "JUnit rules" in section.summary
    assert any("Rule" in evidence.snippet for evidence in section.evidence)


def test_deep_links_are_an_inventory(fixture_profile: Profile) -> None:
    section = fixture_profile.find_section("08_ui_testing", "deep_link_inventory")
    assert section is not None and section.detected
    assert section.kind is ResultKind.INVENTORY
    assert section.items == ["https://${deepLinkHost}"]
    assert section.evidence_total == len(section.items)
    assert section.inventory_completeness is InventoryCompleteness.UNKNOWN
    assert section.item_evidence[section.items[0]]


def test_exported_components_are_listed(fixture_profile: Profile) -> None:
    section = fixture_profile.find_section("08_ui_testing", "exported_components")
    assert section is not None and section.detected
    assert any("MainActivity" in item for item in section.items)


def test_test_tags_are_listed_without_truncation(fixture_profile: Profile) -> None:
    section = fixture_profile.find_section("08_ui_testing", "test_tag_inventory")
    assert section is not None and section.detected
    assert section.items == [
        "testTag: login_screen",
        "testTag: login_email",
        "testTag: primary_button",
    ]
    assert not section.truncated
    assert section.inventory_completeness is InventoryCompleteness.COMPLETE
    assert all(section.item_evidence[item] for item in section.items)


def test_inventories_are_not_capped_by_the_evidence_limit(fixture_repo: Path) -> None:
    from coador.scanner import scan

    profile = scan(fixture_repo, evidence_limit=1)
    section = profile.find_section("08_ui_testing", "test_tag_inventory")
    assert section is not None
    assert len(section.items) == 3, "an inventory must stay complete"
    assert len(section.evidence) == 1, "the evidence below it is still a sample"


def test_inventory_collects_multiple_selectors_per_line_with_provenance(tmp_path: Path) -> None:
    from coador.scanner import scan

    (tmp_path / "settings.gradle.kts").write_text('rootProject.name = "x"\n')
    source = tmp_path / "app/src/main/java/Selectors.kt"
    source.parent.mkdir(parents=True)
    source.write_text(
        'Modifier.testTag("one").testTag("two")\nModifier.testTag("one")\n',
        encoding="utf-8",
    )
    layout = tmp_path / "app/src/main/res/layout/main.xml"
    layout.parent.mkdir(parents=True)
    layout.write_text(
        '<Root android:id="@+id/first"><View android:id="@+id/second" /></Root>\n',
        encoding="utf-8",
    )

    section = scan(tmp_path).find_section("08_ui_testing", "test_tag_inventory")

    assert section is not None
    assert section.items == [
        "testTag: one",
        "testTag: two",
        "view id: first",
        "view id: second",
    ]
    assert len(section.item_evidence["testTag: one"]) == 2


def test_inventory_discloses_when_its_collection_limit_is_reached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import coador.detectors.test_runtime as runtime
    from coador.scanner import scan

    monkeypatch.setattr(runtime, "INVENTORY_MAX_MATCHES", 2)
    (tmp_path / "settings.gradle.kts").write_text('rootProject.name = "x"\n')
    source = tmp_path / "app/src/main/java/Selectors.kt"
    source.parent.mkdir(parents=True)
    source.write_text(
        "\n".join(f'Modifier.testTag("tag_{index}")' for index in range(3)),
        encoding="utf-8",
    )

    section = scan(tmp_path).find_section("08_ui_testing", "test_tag_inventory")

    assert section is not None
    assert section.items == ["testTag: tag_0", "testTag: tag_1"]
    assert section.inventory_completeness is InventoryCompleteness.INCOMPLETE
    assert section.collection_limit == 2
    assert section.collection_stop_reason == "Collection limit reached"


def test_manifest_inventories_parse_xml_edges_without_claiming_merged_truth(
    tmp_path: Path,
) -> None:
    from coador.scanner import scan

    (tmp_path / "settings.gradle.kts").write_text('rootProject.name = "x"\n')
    manifest = tmp_path / "app/src/main/AndroidManifest.xml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """<manifest xmlns:android="http://schemas.android.com/apk/res/android">
  <application>
    <activity android:name=".Main" android:exported="true">
      <intent-filter>
        <data
          android:scheme="https"
          android:host="example.com"
          android:port="8443"
          android:pathPrefix="/open" />
        <data android:scheme="custom" />
      </intent-filter>
    </activity>
    <activity-alias android:name=".Alias" android:exported="true" />
    <service android:name=".PrivateService" android:exported="false" />
    <receiver android:name=".LegacyReceiver"><intent-filter /></receiver>
  </application>
</manifest>
""",
        encoding="utf-8",
    )
    duplicate = tmp_path / "feature/src/main/AndroidManifest.xml"
    duplicate.parent.mkdir(parents=True)
    duplicate.write_text(
        """<manifest xmlns:android="http://schemas.android.com/apk/res/android">
  <application><activity android:name=".Other" android:exported="false">
    <intent-filter><data android:scheme="custom" /></intent-filter>
  </activity></application>
</manifest>
""",
        encoding="utf-8",
    )

    profile = scan(tmp_path)
    links = profile.find_section("08_ui_testing", "deep_link_inventory")
    components = profile.find_section("08_ui_testing", "exported_components")

    assert links is not None
    assert links.items == ["https://example.com:8443/open", "custom://*"]
    assert len(links.item_evidence["custom://*"]) == 2
    assert all(
        evidence.provenance is Provenance.FILE for evidence in links.item_evidence["custom://*"]
    )
    assert links.inventory_completeness is InventoryCompleteness.UNKNOWN
    assert any("not merged" in limitation for limitation in links.limitations)

    assert components is not None
    assert components.items == ["activity .Main", "activity-alias .Alias"]
    assert all("PrivateService" not in item for item in components.items)
    assert any("implicit exported state" in item for item in components.limitations)


def test_java_test_helpers_and_groovy_tasks_are_observed(tmp_path: Path) -> None:
    from coador.scanner import scan

    (tmp_path / "settings.gradle").write_text("rootProject.name = 'x'\n")
    build = tmp_path / "app/build.gradle"
    build.parent.mkdir()
    build.write_text("tasks.register('connectedDemoAndroidTest')\n", encoding="utf-8")
    helper = tmp_path / "app/src/androidTest/java/example/LoginScreen.java"
    helper.parent.mkdir(parents=True)
    helper.write_text(
        """package example.screens;
public class LoginScreen implements TestRule {
  public void login() { takeScreenshot(); }
}
""",
        encoding="utf-8",
    )
    test_class = tmp_path / "app/src/androidTest/java/example/LoginTest.java"
    test_class.write_text("package example; public class LoginTest {}\n", encoding="utf-8")

    profile = scan(tmp_path)

    tasks = profile.find_section("07_testing", "test_tasks")
    entry_points = profile.find_section("07_testing", "test_entry_points")
    screens = profile.find_section("08_ui_testing", "screen_names_inventory")
    classes = profile.find_section("08_ui_testing", "ui_test_class_names")
    login = profile.find_section("08_ui_testing", "login_auth_helpers")

    assert tasks is not None and "connectedDemoAndroidTest" in tasks.summary
    assert entry_points is not None and "JUnit rules" in entry_points.summary
    assert screens is not None and screens.detected
    assert any("LoginScreen" in evidence.snippet for evidence in screens.evidence)
    assert classes is not None and classes.detected
    assert any("LoginTest" in evidence.snippet for evidence in classes.evidence)
    assert login is not None and login.detected and "Login helpers" in login.summary


def test_qa_acceptance_questions_have_evidence_or_explicit_limits(
    fixture_profile: Profile,
) -> None:
    question_sections = [
        ("07_testing", "instrumentation_runner"),
        ("07_testing", "test_tasks"),
        ("07_testing", "test_dependency_substitution"),
        ("07_testing", "test_entry_points"),
        ("08_ui_testing", "test_tag_inventory"),
        ("08_ui_testing", "deep_link_inventory"),
        ("08_ui_testing", "exported_components"),
        ("09_ci_cd", "artifacts_and_reports"),
    ]
    for layer_id, section_id in question_sections:
        section = fixture_profile.find_section(layer_id, section_id)
        assert section is not None
        assert section.evidence or section.limitations
        if section.detected:
            assert section.evidence

    tasks = fixture_profile.find_section("07_testing", "test_tasks")
    reports = fixture_profile.find_section("09_ci_cd", "artifacts_and_reports")
    assert tasks is not None and tasks.summary.startswith("Observed task references:")
    assert reports is not None and "app/build/test-results/**/*.xml" in reports.summary


def test_a_project_without_tests_reports_no_runtime(tmp_path: Path) -> None:
    from coador.detectors.test_runtime import get_test_runtime_detectors

    (tmp_path / "settings.gradle.kts").write_text('rootProject.name = "x"\n', encoding="utf-8")
    for detector in get_test_runtime_detectors(tmp_path):
        assert not detector.detect().detected, detector.name
