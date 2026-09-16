"""Detectors that answer "how do I run the tests of this project".

The other test layers describe what exists; these describe how it is executed:
which runner, which Gradle tasks, how dependencies are replaced, and which
entry points a new test would extend.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from coador.detectors.base import BaseDetector, DetectionResult, Evidence
from coador.model import InventoryCompleteness
from coador.textscan import glob_files, grep_files, read_file_content

# Inventory collection has a separate, explicitly reported cap.
INVENTORY_MAX_MATCHES = 5000
ANDROID_NAMESPACE = "http://schemas.android.com/apk/res/android"

GRADLE_GLOBS = ("**/*.gradle", "**/*.gradle.kts")
TEST_SOURCE_GLOBS = ("**/androidTest/**/*.kt", "**/androidTest/**/*.java")
UNIT_TEST_GLOBS = ("**/test/**/*.kt", "**/test/**/*.java")


class InstrumentationRunnerDetector(BaseDetector):
    """The runner that executes instrumentation tests, and the Application it starts."""

    @property
    def name(self) -> str:
        return "Instrumentation Runner"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        findings: list[str] = []

        runners: set[str] = set()
        for match in grep_files(
            self.repo_root, r"testInstrumentationRunner\s*[=\s]\s*['\"]([^'\"]+)['\"]", GRADLE_GLOBS
        ):
            evidence.append(
                Evidence.from_match(
                    self.relative_path(match.file_path), match.line_number, match.line_content
                )
            )
            found = re.search(r"['\"]([^'\"]+)['\"]", match.line_content)
            if found:
                runners.add(found.group(1))
        if runners:
            findings.append(f"runner: {', '.join(sorted(runners))}")

        custom = grep_files(
            self.repo_root,
            r"class\s+(\w+)\s*:\s*AndroidJUnitRunner|extends\s+AndroidJUnitRunner",
            TEST_SOURCE_GLOBS,
        )
        for match in custom:
            evidence.append(
                Evidence.from_match(
                    self.relative_path(match.file_path), match.line_number, match.line_content
                )
            )
        if custom:
            findings.append("custom runner class")

        applications = grep_files(
            self.repo_root,
            r"newApplication\s*\(|HiltTestApplication|TestApplication::class",
            TEST_SOURCE_GLOBS,
        )
        for match in applications:
            evidence.append(
                Evidence.from_match(
                    self.relative_path(match.file_path), match.line_number, match.line_content
                )
            )
        if applications:
            findings.append("test Application override")

        orchestrator = grep_files(
            self.repo_root,
            r"ANDROIDX_TEST_ORCHESTRATOR|androidx_test_orchestrator|clearPackageData|"
            r"androidx\.test:orchestrator",
            (*GRADLE_GLOBS, "gradle/libs.versions.toml"),
        )
        for match in orchestrator:
            evidence.append(
                Evidence.from_match(
                    self.relative_path(match.file_path), match.line_number, match.line_content
                )
            )
        if orchestrator:
            findings.append("Android Test Orchestrator")

        if findings:
            return DetectionResult(
                detected=True,
                description="Observed: " + "; ".join(findings),
                evidence=evidence,
                limitations=[
                    "Static scanning cannot resolve runner configuration supplied only by "
                    "convention plugins or generated build logic"
                ],
            )
        return DetectionResult(
            detected=False,
            description="No instrumentation runner observed",
            limitations=[
                "Missing static evidence does not exclude convention-plugin or generated "
                "runner configuration"
            ],
        )


class TestTasksDetector(BaseDetector):
    """The Gradle tasks that run the tests, including the variant-specific ones."""

    @property
    def name(self) -> str:
        return "Test Tasks"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        tasks: set[str] = set()

        for match in grep_files(
            self.repo_root,
            r"tasks\.register\s*[<(]\s*[\"']?(\w*[Tt]est\w*)|tasks\.create\s*\(\s*[\"'](\w*[Tt]est\w*)",
            GRADLE_GLOBS,
        ):
            evidence.append(
                Evidence.from_match(
                    self.relative_path(match.file_path), match.line_number, match.line_content
                )
            )
            found = re.search(r"[\"'](\w*[Tt]est\w*)[\"']", match.line_content)
            if found:
                tasks.add(found.group(1))

        for match in grep_files(
            self.repo_root,
            r"\b(connected\w*AndroidTest|test\w*UnitTest|connectedCheck|managedDevices?\w*)\b",
            (*GRADLE_GLOBS, "**/*.yml", "**/*.yaml", "**/*.sh", "Makefile", "**/*.md"),
        ):
            evidence.append(
                Evidence.from_match(
                    self.relative_path(match.file_path), match.line_number, match.line_content
                )
            )
            tasks.add(match.match_text)

        managed = grep_files(
            self.repo_root, r"managedDevices|localDevices|gradleManagedDevice", GRADLE_GLOBS
        )
        for match in managed:
            evidence.append(
                Evidence.from_match(
                    self.relative_path(match.file_path), match.line_number, match.line_content
                )
            )

        if not tasks and not managed:
            return DetectionResult.not_found("No test tasks referenced in the repository")

        summary = (
            "Observed task references: " + ", ".join(sorted(tasks)[:8])
            if tasks
            else "Observed Gradle managed-device configuration"
        )
        if managed:
            summary += "; Gradle managed devices"
        return DetectionResult(
            detected=True,
            description=summary,
            evidence=evidence,
            limitations=[
                "Referenced task names are not a Gradle enumeration and may not be executable "
                "in every variant"
            ],
        )


class TestDependencySubstitutionDetector(BaseDetector):
    """How production dependencies are replaced while tests run."""

    MECHANISMS: tuple[tuple[str, str], ...] = (
        ("Hilt test modules", r"@TestInstallIn|@UninstallModules|@BindValue"),
        ("Hilt test entry point", r"@HiltAndroidTest|HiltAndroidRule"),
        ("MockWebServer", r"MockWebServer|mockwebserver"),
        ("WireMock", r"WireMockServer|wiremock"),
        ("Fake implementations", r"\b(class|object)\s+Fake\w+"),
        ("Test doubles module", r"@Module[\s\S]{0,80}Test|TestAppModule|TestNetworkModule"),
        ("Robolectric", r"@RunWith\s*\(\s*RobolectricTestRunner|robolectric"),
    )

    @property
    def name(self) -> str:
        return "Test Dependency Substitution"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        found: list[str] = []

        for mechanism, pattern in self.MECHANISMS:
            matches = grep_files(self.repo_root, pattern, (*TEST_SOURCE_GLOBS, *UNIT_TEST_GLOBS))
            if not matches:
                continue
            found.append(mechanism)
            evidence.extend(
                Evidence.from_match(
                    self.relative_path(match.file_path), match.line_number, match.line_content
                )
                for match in matches
            )

        if found:
            return DetectionResult(
                detected=True,
                description="Observed: " + ", ".join(found),
                evidence=evidence,
                limitations=[
                    "Name and annotation matching does not establish the runtime dependency graph"
                ],
            )
        return DetectionResult(
            detected=False,
            description="No test dependency substitution observed",
            limitations=[
                "Missing heuristic evidence is not proof that tests use production bindings"
            ],
        )


class TestEntryPointsDetector(BaseDetector):
    """The base classes and helpers a new test is expected to build on."""

    @property
    def name(self) -> str:
        return "Test Entry Points"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        findings: list[str] = []

        base_classes = grep_files(
            self.repo_root,
            r"\b(abstract\s+class|open\s+class)\s+(Base\w*Test\w*|\w*TestCase)\b",
            (*TEST_SOURCE_GLOBS, *UNIT_TEST_GLOBS),
        )
        for match in base_classes:
            evidence.append(
                Evidence.from_match(
                    self.relative_path(match.file_path), match.line_number, match.line_content
                )
            )
        if base_classes:
            findings.append(f"{len(base_classes)} base test classes")

        rules = grep_files(
            self.repo_root,
            r"\bclass\s+\w+Rule\b|:\s*TestWatcher\b|implements\s+TestRule",
            (*TEST_SOURCE_GLOBS, *UNIT_TEST_GLOBS),
        )
        for match in rules:
            evidence.append(
                Evidence.from_match(
                    self.relative_path(match.file_path), match.line_number, match.line_content
                )
            )
        if rules:
            findings.append(f"{len(rules)} custom JUnit rules")

        helper_files = glob_files(
            self.repo_root,
            (
                "**/androidTest/**/*Robot.kt",
                "**/androidTest/**/*Robot.java",
                "**/androidTest/**/*Screen.kt",
                "**/androidTest/**/*Screen.java",
                "**/androidTest/**/*Helper*.kt",
                "**/androidTest/**/*Helper*.java",
                "**/androidTest/**/*Util*.kt",
                "**/androidTest/**/*Util*.java",
                "**/test/**/*Helper*.kt",
                "**/test/**/*Helper*.java",
            ),
        )
        for path in helper_files[:40]:
            evidence.append(
                Evidence(
                    file_path=self.relative_path(path),
                    line_start=1,
                    line_end=1,
                    snippet="test helper",
                )
            )
        if helper_files:
            findings.append(f"{len(helper_files)} screen/robot/helper files")

        if findings:
            return DetectionResult(
                detected=True,
                description="Observed: " + "; ".join(findings),
                evidence=evidence,
                limitations=[
                    "Extension points are name-based candidates and are not ranked or inferred as "
                    "mandatory architecture"
                ],
            )
        return DetectionResult(
            detected=False,
            description="No shared test entry points observed",
            limitations=["Unconventionally named helpers may not be recognized"],
        )


class DeepLinkInventoryDetector(BaseDetector):
    """Deep-link data declarations observed in unmerged source manifests."""

    @property
    def name(self) -> str:
        return "Deep Link Inventory"

    def detect(self) -> DetectionResult:
        manifests = glob_files(self.repo_root, "**/AndroidManifest.xml")
        findings: list[tuple[str, Evidence]] = []
        parse_failures = 0

        for manifest in manifests:
            content = read_file_content(manifest, root=self.repo_root)
            if not content:
                continue
            try:
                root = ET.fromstring(content)
            except ET.ParseError:
                parse_failures += 1
                continue
            for intent_filter in root.iter():
                if _local_name(intent_filter.tag) != "intent-filter":
                    continue
                for element in intent_filter:
                    if _local_name(element.tag) != "data":
                        continue
                    scheme = _android_attribute(element, "scheme")
                    host = _android_attribute(element, "host")
                    if not scheme and not host:
                        continue
                    value = f"{scheme or '*'}://{host or '*'}"
                    port = _android_attribute(element, "port")
                    if port:
                        value += f":{port}"
                    for name in ("path", "pathPrefix", "pathPattern", "pathAdvancedPattern"):
                        path = _android_attribute(element, name)
                        if path:
                            value += path
                            break
                    evidence = Evidence(self.relative_path(manifest), 1, 1, value)
                    findings.append((value, evidence))

        values = list(dict.fromkeys(value for value, _ in findings))
        limitations = ["Static source manifests were not merged and placeholders were not resolved"]
        if parse_failures:
            limitations.append(f"{parse_failures} manifests could not be parsed")
        description = (
            f"{len(values)} deep links declared across {len(manifests)} manifests"
            if values
            else "No deep links observed in parseable source manifests"
        )
        return DetectionResult.inventory(
            description,
            findings,
            completeness=InventoryCompleteness.UNKNOWN,
            limitations=limitations,
        )


class ExportedComponentsDetector(BaseDetector):
    """Components other apps and test tooling can launch directly."""

    @property
    def name(self) -> str:
        return "Exported Components"

    def detect(self) -> DetectionResult:
        manifests = glob_files(self.repo_root, "**/AndroidManifest.xml")
        findings: list[tuple[str, Evidence]] = []
        parse_failures = 0
        implicit_candidates = 0

        for manifest in manifests:
            content = read_file_content(manifest, root=self.repo_root)
            if not content:
                continue
            try:
                root = ET.fromstring(content)
            except ET.ParseError:
                parse_failures += 1
                continue
            for element in root.iter():
                component_type = _local_name(element.tag)
                if component_type not in {
                    "activity",
                    "activity-alias",
                    "service",
                    "receiver",
                    "provider",
                }:
                    continue
                name = _android_attribute(element, "name")
                if not name:
                    continue
                exported = _android_attribute(element, "exported")
                if exported != "true":
                    if exported is None and any(
                        _local_name(child.tag) == "intent-filter" for child in element
                    ):
                        implicit_candidates += 1
                    continue
                value = f"{component_type} {name}"
                evidence = Evidence(self.relative_path(manifest), 1, 1, f"{value} (exported)")
                findings.append((value, evidence))

        values = list(dict.fromkeys(value for value, _ in findings))
        limitations = ["Static source manifests were not merged"]
        if implicit_candidates:
            limitations.append(
                f"{implicit_candidates} components have implicit exported state "
                "requiring API context"
            )
        if parse_failures:
            limitations.append(f"{parse_failures} manifests could not be parsed")
        description = (
            f"{len(values)} explicitly exported components"
            if values
            else "No explicitly exported components observed in parseable source manifests"
        )
        return DetectionResult.inventory(
            description,
            findings,
            completeness=InventoryCompleteness.UNKNOWN,
            limitations=limitations,
        )


class TestTagInventoryDetector(BaseDetector):
    """Every Compose test tag, which is what a UI test selects on."""

    @property
    def name(self) -> str:
        return "Test Tag Inventory"

    def detect(self) -> DetectionResult:
        candidates: list[tuple[str, Evidence]] = []

        tag_matches = grep_files(
            self.repo_root,
            r"testTag\s*\(\s*[\"']([^\"']+)[\"']|testTag\s*=\s*[\"']([^\"']+)[\"']",
            ("**/*.kt",),
            max_matches=INVENTORY_MAX_MATCHES + 1,
            all_matches_per_line=True,
        )
        for match in tag_matches:
            found = re.search(r"[\"']([^\"']+)[\"']", match.match_text)
            if not found:
                continue
            value = f"testTag: {found.group(1)}"
            candidates.append(
                (
                    value,
                    self.source_evidence(
                        match.file_path, match.line_number, match.line_number, value
                    ),
                )
            )

        resource_ids = grep_files(
            self.repo_root,
            r'android:id\s*=\s*"@\+id/(\w+)"',
            ("**/*.xml",),
            max_matches=INVENTORY_MAX_MATCHES + 1,
            all_matches_per_line=True,
        )
        for match in resource_ids:
            found = re.search(r"@\+id/(\w+)", match.match_text)
            if not found:
                continue
            value = f"view id: {found.group(1)}"
            candidates.append(
                (
                    value,
                    self.source_evidence(
                        match.file_path,
                        match.line_number,
                        match.line_number,
                        value,
                    ),
                )
            )

        capped = len(candidates) > INVENTORY_MAX_MATCHES
        findings = candidates[:INVENTORY_MAX_MATCHES]
        values = list(dict.fromkeys(value for value, _ in findings))
        parts = []
        tags = sum(value.startswith("testTag: ") for value in values)
        ids = sum(value.startswith("view id: ") for value in values)
        if tags:
            parts.append(f"{tags} Compose test tags")
        if ids:
            parts.append(f"{ids} view ids")
        description = ", ".join(parts) if parts else "No literal test tags or view ids found"
        return DetectionResult.inventory(
            description,
            findings,
            completeness=(
                InventoryCompleteness.INCOMPLETE if capped else InventoryCompleteness.COMPLETE
            ),
            collection_limit=INVENTORY_MAX_MATCHES,
            stop_reason="Collection limit reached" if capped else None,
            limitations=[
                "Only literal Compose testTag values and declared @+id XML resources are collected"
            ],
        )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _android_attribute(element: ET.Element, name: str) -> str | None:
    return element.get(f"{{{ANDROID_NAMESPACE}}}{name}") or element.get(f"android:{name}")


def get_test_runtime_detectors(repo_root: Path) -> list[BaseDetector]:
    return [
        InstrumentationRunnerDetector(repo_root),
        TestTasksDetector(repo_root),
        TestDependencySubstitutionDetector(repo_root),
        TestEntryPointsDetector(repo_root),
        DeepLinkInventoryDetector(repo_root),
        ExportedComponentsDetector(repo_root),
        TestTagInventoryDetector(repo_root),
    ]
