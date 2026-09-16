from __future__ import annotations

import re
from pathlib import Path

from coador.detectors.base import BaseDetector, DetectionResult, Evidence
from coador.textscan import glob_files, grep_files, read_file_content

ANDROID_TEST_SOURCE_GLOBS = ("**/androidTest/**/*.kt", "**/androidTest/**/*.java")


class UITestFrameworkLocationDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "UI Test Framework Location"

    @property
    def category(self) -> str:
        return "Test Framework"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        locations: list[str] = []

        android_test_dirs = self.find_dirs({"androidTest"})
        for d in android_test_dirs:
            rel_path = self.relative_path(d)
            locations.append(rel_path)
            evidence.append(
                Evidence(
                    file_path=rel_path,
                    line_start=1,
                    line_end=1,
                    snippet="androidTest source set",
                )
            )

        screen_packages = grep_files(
            self.repo_root,
            r"package\s+[\w.]+\.(?:screen|screens|robot|robots)",
            ANDROID_TEST_SOURCE_GLOBS,
        )
        for m in screen_packages:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        if locations:
            return DetectionResult(
                detected=True,
                description=f"Found {len(locations)} androidTest locations",
                evidence=evidence,
            )

        return DetectionResult.not_found("No UI test locations found")


class ScreenObjectsInventoryDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Screen Objects Inventory"

    @property
    def category(self) -> str:
        return "Page Objects"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        screen_files: list[Path] = []

        patterns = ["**/androidTest/**/*Screen.kt", "**/androidTest/**/*Screen.java"]

        for pattern in patterns:
            found = glob_files(self.repo_root, pattern)
            screen_files.extend(found)

        screen_files = sorted(set(screen_files))

        for sf in screen_files:
            evidence.append(
                Evidence(
                    file_path=self.relative_path(sf),
                    line_start=1,
                    line_end=1,
                    snippet=sf.name,
                )
            )

        if screen_files:
            return DetectionResult(
                detected=True,
                description=f"Found {len(screen_files)} Screen/Robot/Page objects",
                evidence=evidence,
            )

        return DetectionResult.not_found("No Screen objects found")


class ScreenNamesInventoryDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Screen Names Inventory"

    @property
    def category(self) -> str:
        return "Page Objects"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        names: list[str] = []

        class_re = re.compile(r"\b(class|object)\s+([A-Za-z0-9_]+Screen)\b")
        matches = grep_files(
            self.repo_root,
            class_re,
            ANDROID_TEST_SOURCE_GLOBS,
        )
        for m in matches:
            match = class_re.search(m.line_content)
            if not match:
                continue
            name = match.group(2)
            names.append(name)
            evidence.append(
                Evidence(
                    file_path=self.relative_path(m.file_path),
                    line_start=m.line_number,
                    line_end=m.line_number,
                    snippet=f"Screen: {name}",
                )
            )

        uniq_names = sorted(set(names))
        if uniq_names:
            return DetectionResult(
                detected=True,
                description=f"Found {len(uniq_names)} Screen classes",
                evidence=evidence,
            )

        return DetectionResult.not_found("No Screen class names found")


class UITestClassNamesDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "UI Test Class Names"

    @property
    def category(self) -> str:
        return "Test Organization"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        names: list[str] = []

        class_re = re.compile(r"\bclass\s+([A-Za-z0-9_]+Test)\b")
        matches = grep_files(
            self.repo_root,
            class_re,
            ANDROID_TEST_SOURCE_GLOBS,
        )
        for m in matches:
            match = class_re.search(m.line_content)
            if not match:
                continue
            name = match.group(1)
            names.append(name)
            evidence.append(
                Evidence(
                    file_path=self.relative_path(m.file_path),
                    line_start=m.line_number,
                    line_end=m.line_number,
                    snippet=f"Test: {name}",
                )
            )

        uniq_names = sorted(set(names))
        if uniq_names:
            return DetectionResult(
                detected=True,
                description=f"Found {len(uniq_names)} UI test classes",
                evidence=evidence,
            )

        return DetectionResult.not_found("No UI test class names found")


class UITestApplicationDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "UI Test Application Class"

    @property
    def category(self) -> str:
        return "Test Infrastructure"

    def _detect_di_mode(self, evidence: list[Evidence]) -> str:
        """Name the DI framework used by the instrumentation tests.

        Hilt is checked first on purpose: it is built on Dagger, so a Hilt
        project matches every Dagger marker as well.
        """
        build_globs = (
            "**/*gradle*",
            "**/gradle/libs.versions.toml",
            "**/androidTest/**/*.kt",
            "**/androidTest/**/*.java",
        )

        hilt_matches = grep_files(
            self.repo_root,
            r"\bhilt\b|dagger\.hilt|HiltAndroidTest|HiltTestApplication",
            build_globs,
        )
        if hilt_matches:
            for m in hilt_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )
            return "Hilt"

        dagger_matches = grep_files(
            self.repo_root,
            r"\bdagger\b|com\.google\.dagger",
            build_globs,
        )
        if dagger_matches:
            for m in dagger_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )
            return "Dagger"

        return "None"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        candidates: set[str] = set()

        di_mode = self._detect_di_mode(evidence)

        manifest_matches = grep_files(
            self.repo_root,
            r'android:name\s*=\s*"([^"]+)"',
            "**/androidTest/**/AndroidManifest.xml",
        )
        for m in manifest_matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )
            match = re.search(r'android:name\s*=\s*"([^"]+)"', m.line_content)
            if match:
                candidates.add(match.group(1))

        runner_matches = grep_files(
            self.repo_root,
            r"testInstrumentationRunner\s+['\"]([^'\"]+)['\"]",
            ("**/*build.gradle*", "**/gradle/libs.versions.toml"),
        )
        for m in runner_matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        runner_files = []
        runner_files.extend(glob_files(self.repo_root, "**/*Runner*.kt"))
        runner_files.extend(glob_files(self.repo_root, "**/*Runner*.java"))

        new_app_string = re.compile(r'newApplication\([^)]*?"([A-Za-z0-9_$.]+)"')
        new_app_kotlin = re.compile(
            r"newApplication\([^)]*?([A-Za-z0-9_]+)::class\.java(?:\.name)?"
        )
        new_app_java = re.compile(
            r"newApplication\([^)]*?([A-Za-z0-9_$.]+)\.class(?:\.getName\(\))?"
        )

        for rf in sorted(set(runner_files)):
            content = read_file_content(rf, root=self.repo_root) or ""
            if "newApplication" not in content:
                continue
            for line_no, line in enumerate(content.splitlines(), start=1):
                if "newApplication" not in line:
                    continue
                evidence.append(
                    Evidence(
                        file_path=self.relative_path(rf),
                        line_start=line_no,
                        line_end=line_no,
                        snippet=line.strip(),
                    )
                )
                for pattern in (new_app_string, new_app_kotlin, new_app_java):
                    match = pattern.search(line)
                    if match:
                        candidates.add(match.group(1))

        custom_test_app = grep_files(
            self.repo_root,
            r"@CustomTestApplication\(",
            ANDROID_TEST_SOURCE_GLOBS,
        )
        for m in custom_test_app:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        if candidates:
            prefix = f"{di_mode} detected; " if di_mode != "None" else ""
            return DetectionResult(
                detected=True,
                description=(
                    f"{prefix}Test application class candidates: {', '.join(sorted(candidates))}"
                ),
                evidence=evidence,
            )

        if evidence:
            prefix = f"{di_mode} detected; " if di_mode != "None" else ""
            return DetectionResult(
                detected=True,
                description=f"{prefix}No test application class detected",
                evidence=evidence,
            )

        return DetectionResult.not_found("No test application class signals found")


class ScenariosDirectoryDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Scenarios Directory"

    @property
    def category(self) -> str:
        return "Test Organization"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        scenario_dirs = self.find_dirs({"scenarios"})

        total_files = 0
        for sd in scenario_dirs:
            if "androidTest" not in sd.parts:
                continue
            scenario_dir = self.relative_path(sd)
            source_files = self.glob((f"{scenario_dir}/**/*.kt", f"{scenario_dir}/**/*.java"))
            total_files += len(source_files)
            evidence.append(
                Evidence(
                    file_path=self.relative_path(sd),
                    line_start=1,
                    line_end=1,
                    snippet=f"scenarios/ ({len(source_files)} files)",
                )
            )

        if evidence:
            return DetectionResult(
                detected=True,
                description=f"Found {len(evidence)} scenarios directories, {total_files} files",
                evidence=evidence,
            )

        return DetectionResult.not_found("No scenarios directories found")


class ComposeSelectorsDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Compose Selectors Convention"

    @property
    def category(self) -> str:
        return "Compose Testing"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        semantics_matches = grep_files(
            self.repo_root,
            r"\.semantics\s*\{\s*testTag\s*=",
            "**/*.kt",
        )
        for m in semantics_matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        modifier_matches = grep_files(
            self.repo_root,
            r"Modifier\.testTag\s*\(",
            "**/*.kt",
        )
        for m in modifier_matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        if evidence:
            total = len(semantics_matches) + len(modifier_matches)
            return DetectionResult(
                detected=True,
                description=f"Found {total} testTag usages",
                evidence=evidence,
            )

        return DetectionResult.not_found("No Compose testTag selectors found")


class KaspressoDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Kaspresso Framework"

    @property
    def category(self) -> str:
        return "Test Framework"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        toml_path = self.find_file("gradle/libs.versions.toml")
        if toml_path:
            content = (read_file_content(toml_path, root=self.repo_root) or "").lower()
            if "kaspresso" in content:
                matches = grep_files(self.repo_root, r"kaspresso", "gradle/libs.versions.toml")
                for m in matches:
                    evidence.append(
                        Evidence.from_match(
                            self.relative_path(m.file_path), m.line_number, m.line_content
                        )
                    )

        kaspresso_imports = grep_files(
            self.repo_root,
            r"import\s+com\.kaspersky\.kaspresso",
            ANDROID_TEST_SOURCE_GLOBS,
        )
        for m in kaspresso_imports:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        testcase_matches = grep_files(
            self.repo_root,
            r":\s*TestCase[<(]|TestCaseRule",
            ANDROID_TEST_SOURCE_GLOBS,
        )
        for m in testcase_matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        if evidence:
            return DetectionResult(
                detected=True,
                description="Kaspresso test framework",
                evidence=evidence,
            )

        return DetectionResult.not_found("Kaspresso not detected")


class StepDSLDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Step DSL / Helpers"

    @property
    def category(self) -> str:
        return "Test DSL"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        features: list[str] = []

        step_matches = grep_files(
            self.repo_root,
            r'\bstep\s*\(\s*["\']',
            ANDROID_TEST_SOURCE_GLOBS,
        )
        if step_matches:
            features.append("step DSL")
            for m in step_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        flaky_matches = grep_files(
            self.repo_root,
            r"flakySafely\s*\{|flakySafely\s*\(",
            ANDROID_TEST_SOURCE_GLOBS,
        )
        if flaky_matches:
            features.append("flakySafely")
            for m in flaky_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        scenario_matches = grep_files(
            self.repo_root,
            r"Scenario\s*\(|scenario\s*\{",
            ANDROID_TEST_SOURCE_GLOBS,
        )
        if scenario_matches:
            features.append("Scenario")
            for m in scenario_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        if features:
            return DetectionResult(
                detected=True,
                description=", ".join(features),
                evidence=evidence,
            )

        return DetectionResult.not_found("No Step DSL detected")


class DeterminismHooksDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Determinism Hooks"

    @property
    def category(self) -> str:
        return "Test Infrastructure"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        hooks: list[str] = []

        test_component_matches = grep_files(
            self.repo_root,
            r"Test\w*Component|@TestInstallIn|TestAppComponent",
            ANDROID_TEST_SOURCE_GLOBS,
        )
        if test_component_matches:
            hooks.append("Test DI Component")
            for m in test_component_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        fake_matches = grep_files(
            self.repo_root,
            r"class\s+Fake\w+|class\s+Mock\w+|object\s+Fake\w+",
            ANDROID_TEST_SOURCE_GLOBS,
        )
        if fake_matches:
            hooks.append("Fake implementations")
            for m in fake_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        mock_server_matches = grep_files(
            self.repo_root,
            r"MockWebServer|WireMock|mockServer",
            ANDROID_TEST_SOURCE_GLOBS,
        )
        if mock_server_matches:
            hooks.append("Mock server")
            for m in mock_server_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        if hooks:
            return DetectionResult(
                detected=True,
                description=", ".join(hooks),
                evidence=evidence,
            )

        return DetectionResult.not_found("No determinism hooks detected")


class SynchronizationUtilitiesDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Synchronization Utilities"

    @property
    def category(self) -> str:
        return "Test Synchronization"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        patterns = [
            r"IdlingResource|CountingIdlingResource|IdlingRegistry",
            r"waitFor|waitUntil|awaitIdle|idleSync|waitForIdle",
            r"timeout|retry",
        ]

        for pattern in patterns:
            matches = grep_files(self.repo_root, pattern, ANDROID_TEST_SOURCE_GLOBS)
            for m in matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        if evidence:
            return DetectionResult(
                detected=True,
                description="Synchronization helpers",
                evidence=evidence,
            )

        return DetectionResult.not_found("No synchronization utilities detected")


class DeepLinksWebViewHelpersDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Deep Links / WebView Helpers"

    @property
    def category(self) -> str:
        return "Test Helpers"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        deeplink_matches = grep_files(
            self.repo_root,
            r"deepLink|DeepLink|Intent\.ACTION_VIEW|Uri\.parse",
            ANDROID_TEST_SOURCE_GLOBS,
        )
        for m in deeplink_matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        webview_matches = grep_files(
            self.repo_root,
            r"WebView|WebViewClient|webkit",
            ANDROID_TEST_SOURCE_GLOBS,
        )
        for m in webview_matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        if evidence:
            return DetectionResult(
                detected=True,
                description="Deep links/WebView helpers",
                evidence=evidence,
            )

        return DetectionResult.not_found("No deep link or WebView helpers detected")


class LoginAuthHelpersDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Login/Auth Helpers"

    @property
    def category(self) -> str:
        return "Test Helpers"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        helpers: list[str] = []

        login_matches = grep_files(
            self.repo_root,
            r"fun\s+login|\b(?:void|\w+)\s+login\s*\(|loginAs|performLogin|authenticateUser",
            ANDROID_TEST_SOURCE_GLOBS,
        )
        if login_matches:
            helpers.append("Login helpers")
            for m in login_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        token_matches = grep_files(
            self.repo_root,
            r"injectToken|setTestToken|mockToken",
            ANDROID_TEST_SOURCE_GLOBS,
        )
        if token_matches:
            helpers.append("Token injection")
            for m in token_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        test_user_matches = grep_files(
            self.repo_root,
            r"TestUser|testCredentials|test_users",
            ANDROID_TEST_SOURCE_GLOBS,
        )
        if test_user_matches:
            helpers.append("Test users config")
            for m in test_user_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        if helpers:
            return DetectionResult(
                detected=True,
                description=", ".join(helpers),
                evidence=evidence,
            )

        return DetectionResult.not_found("No login/auth helpers detected")


class UISuiteGroupingDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "UI Suite Grouping"

    @property
    def category(self) -> str:
        return "Test Organization"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        mechanisms: list[str] = []

        annotation_matches = grep_files(
            self.repo_root,
            r"@(Smoke|Sanity|Regression|Quarantine|FlavorFilter)",
            ANDROID_TEST_SOURCE_GLOBS,
        )
        if annotation_matches:
            mechanisms.append("Custom annotations")
            for m in annotation_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.match_text
                    )
                )

        tag_matches = grep_files(
            self.repo_root,
            r'@Tag\s*\(\s*["\']',
            ANDROID_TEST_SOURCE_GLOBS,
        )
        if tag_matches:
            mechanisms.append("JUnit @Tag")
            for m in tag_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        suite_matches = grep_files(
            self.repo_root,
            r"@Suite|@RunWith\(Suite",
            ANDROID_TEST_SOURCE_GLOBS,
        )
        if suite_matches:
            mechanisms.append("JUnit Suite")
            for m in suite_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        if mechanisms:
            return DetectionResult(
                detected=True,
                description=", ".join(mechanisms),
                evidence=evidence,
            )

        return DetectionResult.not_found("No suite grouping detected")


class ReportingHooksDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Reporting Hooks"

    @property
    def category(self) -> str:
        return "Test Reporting"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        hooks: list[str] = []

        allure_matches = grep_files(
            self.repo_root,
            r"@(Step|Attachment|Epic|Feature|Story)|Allure\.",
            ANDROID_TEST_SOURCE_GLOBS,
        )
        if allure_matches:
            hooks.append("Allure")
            for m in allure_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.match_text
                    )
                )

        screenshot_matches = grep_files(
            self.repo_root,
            r"Screenshot|takeScreenshot|captureScreen",
            ANDROID_TEST_SOURCE_GLOBS,
        )
        if screenshot_matches:
            hooks.append("Screenshot capture")
            for m in screenshot_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        listener_matches = grep_files(
            self.repo_root,
            r"TestWatcher|TestListener|RunListener",
            ANDROID_TEST_SOURCE_GLOBS,
        )
        if listener_matches:
            hooks.append("Test listeners")
            for m in listener_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        if hooks:
            return DetectionResult(
                detected=True,
                description=", ".join(hooks),
                evidence=evidence,
            )

        return DetectionResult.not_found("No reporting hooks detected")


def get_ui_testing_detectors(repo_root: Path) -> list[BaseDetector]:
    return [
        UITestFrameworkLocationDetector(repo_root),
        ScreenObjectsInventoryDetector(repo_root),
        ScreenNamesInventoryDetector(repo_root),
        UITestClassNamesDetector(repo_root),
        UITestApplicationDetector(repo_root),
        ScenariosDirectoryDetector(repo_root),
        ComposeSelectorsDetector(repo_root),
        KaspressoDetector(repo_root),
        StepDSLDetector(repo_root),
        SynchronizationUtilitiesDetector(repo_root),
        DeterminismHooksDetector(repo_root),
        LoginAuthHelpersDetector(repo_root),
        DeepLinksWebViewHelpersDetector(repo_root),
        UISuiteGroupingDetector(repo_root),
        ReportingHooksDetector(repo_root),
    ]
