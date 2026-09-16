from __future__ import annotations

from pathlib import Path

from coador.detectors.base import BaseDetector, DetectionResult, Evidence
from coador.textscan import glob_files, grep_files, read_file_content


class TestSourceSetsDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Test Source Sets Map"

    @property
    def category(self) -> str:
        return "Test Structure"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        source_sets: list[str] = []

        test_dirs = self.find_dirs({"test"})
        for td in test_dirs:
            if td.parent.name == "src":
                test_dir = self.relative_path(td)
                has_tests = bool(self.glob((f"{test_dir}/**/*.kt", f"{test_dir}/**/*.java")))
                if has_tests:
                    module_path = self.relative_path(td.parent.parent)
                    source_sets.append(f"{module_path}/test")
                    evidence.append(
                        Evidence(
                            file_path=self.relative_path(td),
                            line_start=1,
                            line_end=1,
                            snippet=f"Unit tests in {module_path}",
                        )
                    )

        android_test_dirs = self.find_dirs({"androidTest"})
        for atd in android_test_dirs:
            if atd.parent.name == "src":
                test_dir = self.relative_path(atd)
                has_tests = bool(self.glob((f"{test_dir}/**/*.kt", f"{test_dir}/**/*.java")))
                if has_tests:
                    module_path = self.relative_path(atd.parent.parent)
                    source_sets.append(f"{module_path}/androidTest")
                    evidence.append(
                        Evidence(
                            file_path=self.relative_path(atd),
                            line_start=1,
                            line_end=1,
                            snippet=f"Android tests in {module_path}",
                        )
                    )

        if evidence:
            return DetectionResult(
                detected=True,
                description=f"{len(source_sets)} test source sets",
                evidence=evidence,
            )

        return DetectionResult.not_found("No test source sets found")


class NonUITestFrameworksDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Non-UI Test Frameworks"

    @property
    def category(self) -> str:
        return "Unit Testing"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        frameworks: list[str] = []

        patterns = [
            (r"org\.junit", "JUnit"),
            (r"io\.kotest", "Kotest"),
            (r"io\.mockk", "MockK"),
            (r"org\.mockito", "Mockito"),
            (r"com\.google\.truth", "Truth"),
            (r"org\.assertj", "AssertJ"),
            (r"kotlinx\.coroutines\.test", "Coroutines Test"),
        ]

        for pattern, name in patterns:
            matches = grep_files(self.repo_root, pattern, "**/*.gradle*")
            if not matches:
                matches = grep_files(self.repo_root, pattern, "**/src/test/**/*.kt")
            if matches:
                frameworks.append(name)
                for m in matches:
                    evidence.append(
                        Evidence.from_match(
                            self.relative_path(m.file_path), m.line_number, m.line_content
                        )
                    )

        if evidence:
            return DetectionResult(
                detected=True,
                description=", ".join(frameworks),
                evidence=evidence,
            )

        return DetectionResult.not_found("No test frameworks found")


class SharedFixturesDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Shared Fixtures/Builders"

    @property
    def category(self) -> str:
        return "Test Infrastructure"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        fixture_dirs = ["fixtures", "testdata", "builders", "testfixtures", "testcommon"]
        for fd in fixture_dirs:
            dirs = self.find_dirs({fd})
            for d in dirs:
                evidence.append(
                    Evidence(
                        file_path=self.relative_path(d),
                        line_start=1,
                        line_end=1,
                        snippet=f"Test fixtures: {d.name}",
                    )
                )

        builder_files = grep_files(self.repo_root, r"class\s+\w+Builder", "**/test/**/*.kt")
        for m in builder_files:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        factory_files = grep_files(
            self.repo_root,
            r"object\s+\w+Factory|fun\s+create\w+",
            "**/test/**/*.kt",
        )
        for m in factory_files:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        if evidence:
            return DetectionResult(
                detected=True,
                description=f"{len(evidence)} fixtures/builders found",
                evidence=evidence,
            )

        return DetectionResult.not_found("No shared fixtures found")


class TestResourcesDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Test Resources"

    @property
    def category(self) -> str:
        return "Test Data"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        resource_dirs = glob_files(self.repo_root, "**/src/test/resources/**/*")
        for r in resource_dirs:
            if r.is_file():
                evidence.append(
                    Evidence(
                        file_path=self.relative_path(r),
                        line_start=1,
                        line_end=1,
                        snippet=r.name,
                    )
                )

        json_files = glob_files(self.repo_root, "**/test/**/*.json")
        for jf in json_files:
            evidence.append(
                Evidence(
                    file_path=self.relative_path(jf),
                    line_start=1,
                    line_end=1,
                    snippet=f"Test JSON: {jf.name}",
                )
            )

        if evidence:
            return DetectionResult(
                detected=True,
                description=f"{len(evidence)} test resources",
                evidence=evidence,
            )

        return DetectionResult.not_found("No test resources found")


class TestConfigKnobsDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Test Config Knobs"

    @property
    def category(self) -> str:
        return "Test Configuration"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        matches = grep_files(self.repo_root, r"testInstrumentationRunner", "**/*.gradle*")
        for m in matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        matches = grep_files(self.repo_root, r"testOptions", "**/*.gradle*")
        for m in matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        test_properties = glob_files(self.repo_root, "**/test*.properties")
        for tp in test_properties:
            evidence.append(
                Evidence(
                    file_path=self.relative_path(tp),
                    line_start=1,
                    line_end=1,
                    snippet=tp.name,
                )
            )

        if evidence:
            return DetectionResult(
                detected=True,
                description="Test configuration",
                evidence=evidence,
            )

        return DetectionResult.not_found("No test config knobs found")


class TestDocsDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Repo Docs About Testing"

    @property
    def category(self) -> str:
        return "Documentation"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        readme_files = glob_files(self.repo_root, "**/README*")
        for rf in readme_files:
            content = (read_file_content(rf, root=self.repo_root) or "").lower()
            if "test" in content:
                evidence.append(
                    Evidence(
                        file_path=self.relative_path(rf),
                        line_start=1,
                        line_end=1,
                        snippet=f"Testing docs: {rf.name}",
                    )
                )

        contributing = glob_files(self.repo_root, "**/CONTRIBUTING*")
        for cf in contributing:
            evidence.append(
                Evidence(
                    file_path=self.relative_path(cf),
                    line_start=1,
                    line_end=1,
                    snippet=cf.name,
                )
            )

        if evidence:
            return DetectionResult(
                detected=True,
                description=f"{len(evidence)} test documentation files",
                evidence=evidence,
            )

        return DetectionResult.not_found("No test documentation found")


def get_testing_detectors(repo_root: Path) -> list[BaseDetector]:
    return [
        TestSourceSetsDetector(repo_root),
        NonUITestFrameworksDetector(repo_root),
        SharedFixturesDetector(repo_root),
        TestResourcesDetector(repo_root),
        TestConfigKnobsDetector(repo_root),
        TestDocsDetector(repo_root),
    ]
