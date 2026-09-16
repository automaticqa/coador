from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from coador.catalog import load_catalog
from coador.detectors.base import BaseDetector, DetectionResult, Evidence
from coador.gradle import (
    parse_include_modules,
    parse_plugins,
    parse_project_dependencies,
)
from coador.paths import UnsafePathError, checked_path
from coador.textscan import glob_files, grep_files, read_file_content


class FullModuleListDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Full Module List"

    @property
    def category(self) -> str:
        return "Modules"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        settings = self.find_file("settings.gradle.kts", "settings.gradle")
        if not settings:
            return DetectionResult.not_found("settings.gradle not found")

        content = read_file_content(settings, root=self.repo_root) or ""
        modules = parse_include_modules(content)

        evidence.append(
            Evidence(
                file_path=self.relative_path(settings),
                line_start=1,
                line_end=1,
                snippet=f"Found {len(modules)} modules",
            )
        )

        lines = content.splitlines()
        line_map: dict[str, int] = {}
        for i, line in enumerate(lines, start=1):
            for module in modules:
                if module in line:
                    line_map.setdefault(module, i)

        for module in modules:
            line_number = line_map.get(module, 1)
            evidence.append(
                Evidence(
                    file_path=self.relative_path(settings),
                    line_start=line_number,
                    line_end=line_number,
                    snippet=module,
                )
            )

        if modules:
            return DetectionResult(
                detected=True,
                description=f"{len(modules)} modules",
                evidence=evidence,
            )

        return DetectionResult.not_found("No modules found in settings.gradle")


class ModuleClassificationDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Module Classification"

    @property
    def category(self) -> str:
        return "Module Types"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        classification: dict[str, list[str]] = defaultdict(list)

        catalog = load_catalog(self.repo_root)
        alias_map = catalog.plugins if catalog else {}

        build_files = glob_files(self.repo_root, "**/build.gradle.kts")
        build_files.extend(glob_files(self.repo_root, "**/build.gradle"))

        for bf in build_files:
            content = read_file_content(bf, root=self.repo_root) or ""
            plugins = parse_plugins(content)
            resolved = [alias_map.get(p, p) for p in plugins]

            module_path = self.relative_path(bf.parent)

            if "com.android.application" in resolved:
                classification["application"].append(module_path)
                match = None
                if "com.android.application" in plugins:
                    match = grep_files(
                        self.repo_root,
                        r"com\.android\.application",
                        self.relative_path(bf),
                    )
                else:
                    for alias in plugins:
                        if alias_map.get(alias) == "com.android.application":
                            match = grep_files(
                                self.repo_root,
                                re.escape(alias),
                                self.relative_path(bf),
                            )
                            if match:
                                break
                if match:
                    evidence.append(
                        Evidence.from_match(
                            self.relative_path(bf),
                            match[0].line_number,
                            f"Application: {module_path}",
                        )
                    )
                else:
                    evidence.append(
                        Evidence(
                            file_path=self.relative_path(bf),
                            line_start=1,
                            line_end=1,
                            snippet=f"Application: {module_path}",
                        )
                    )
            elif "com.android.library" in resolved:
                classification["library"].append(module_path)
                match = None
                if "com.android.library" in plugins:
                    match = grep_files(
                        self.repo_root,
                        r"com\.android\.library",
                        self.relative_path(bf),
                    )
                else:
                    for alias in plugins:
                        if alias_map.get(alias) == "com.android.library":
                            match = grep_files(
                                self.repo_root,
                                re.escape(alias),
                                self.relative_path(bf),
                            )
                            if match:
                                break
                if match:
                    evidence.append(
                        Evidence.from_match(
                            self.relative_path(bf),
                            match[0].line_number,
                            f"Library: {module_path}",
                        )
                    )
            elif "java-library" in resolved or "org.jetbrains.kotlin.jvm" in resolved:
                classification["jvm-library"].append(module_path)

        if classification:
            desc_parts = []
            for type_name, modules in classification.items():
                desc_parts.append(f"{len(modules)} {type_name}")

            return DetectionResult(
                detected=True,
                description=", ".join(desc_parts),
                evidence=evidence,
            )

        return DetectionResult.not_found("No module classification found")


class ModuleDependencyGraphDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Module Dependency Graph"

    @property
    def category(self) -> str:
        return "Dependencies"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        edges: list[tuple[str, str]] = []

        build_files = glob_files(self.repo_root, "**/build.gradle.kts")
        build_files.extend(glob_files(self.repo_root, "**/build.gradle"))

        for bf in build_files:
            content = read_file_content(bf, root=self.repo_root) or ""
            deps = parse_project_dependencies(content)

            if deps:
                source_module = self.relative_path(bf.parent)

                for dep in deps:
                    edges.append((source_module, dep))

                matches = grep_files(
                    self.repo_root,
                    r'project\s*\(\s*["\']:[\w:]+["\']\s*\)',
                    self.relative_path(bf),
                )
                for m in matches:
                    evidence.append(
                        Evidence.from_match(self.relative_path(bf), m.line_number, m.line_content)
                    )

                accessor_matches = grep_files(
                    self.repo_root,
                    r"\bprojects\.[A-Za-z0-9_.]+",
                    self.relative_path(bf),
                )
                for m in accessor_matches:
                    evidence.append(
                        Evidence.from_match(self.relative_path(bf), m.line_number, m.line_content)
                    )

        if edges:
            return DetectionResult(
                detected=True,
                description=f"{len(edges)} inter-module dependencies",
                evidence=evidence,
            )

        return DetectionResult.not_found("No inter-module dependencies found")


class ModuleGroupingDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Module Grouping"

    @property
    def category(self) -> str:
        return "Organization"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        groups: dict[str, list[str]] = defaultdict(list)

        settings = self.find_file("settings.gradle.kts", "settings.gradle")
        if not settings:
            return DetectionResult.not_found("settings.gradle not found")

        content = read_file_content(settings, root=self.repo_root) or ""
        modules = parse_include_modules(content)

        for module in modules:
            parts = module.lstrip(":").split(":")
            if len(parts) >= 2:
                group = parts[0]
                groups[group].append(module)
            else:
                groups["root"].append(module)

        if groups:
            for group, mods in sorted(groups.items(), key=lambda x: -len(x[1])):
                evidence.append(
                    Evidence(
                        file_path=self.relative_path(settings),
                        line_start=1,
                        line_end=1,
                        snippet=f"{group}: {len(mods)} modules",
                    )
                )

            desc_parts = [
                f"{k}({len(v)})" for k, v in sorted(groups.items(), key=lambda x: -len(x[1]))
            ]
            return DetectionResult(
                detected=True,
                description=", ".join(desc_parts),
                evidence=evidence,
            )

        return DetectionResult.not_found("No module grouping found")


class FlavorOverridesDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Flavor Overrides Location"

    @property
    def category(self) -> str:
        return "Flavors"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        flavor_dirs: set[str] = set()

        src_dirs = self.find_dirs({"src"})

        for src_dir in src_dirs:
            for candidate in src_dir.iterdir():
                try:
                    child = checked_path(self.repo_root, candidate, directory=True)
                except UnsafePathError:
                    continue
                source_dirs = []
                for name in ("java", "kotlin", "res"):
                    try:
                        source_dirs.append(
                            checked_path(self.repo_root, child / name, directory=True)
                        )
                    except UnsafePathError:
                        continue
                if (
                    child.is_dir()
                    and child.name
                    not in {
                        "main",
                        "test",
                        "androidTest",
                        "debug",
                        "release",
                    }
                    and any(source_dir.exists() for source_dir in source_dirs)
                ):
                    flavor_dirs.add(child.name)
                    evidence.append(
                        Evidence(
                            file_path=self.relative_path(child),
                            line_start=1,
                            line_end=1,
                            snippet=f"Flavor source set: {child.name}",
                        )
                    )

        if flavor_dirs:
            return DetectionResult(
                detected=True,
                description=(
                    f"{len(flavor_dirs)} flavor source sets: {', '.join(sorted(flavor_dirs))}"
                ),
                evidence=evidence,
            )

        return DetectionResult.not_found("No flavor override directories found")


class UITestsLocationDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "UI Tests Location per Module"

    @property
    def category(self) -> str:
        return "Test Locations"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        modules_with_tests: list[str] = []

        android_test_dirs = self.find_dirs({"androidTest"})

        for atd in android_test_dirs:
            test_dir = self.relative_path(atd)
            has_tests = bool(self.glob((f"{test_dir}/**/*.kt", f"{test_dir}/**/*.java")))

            if has_tests:
                module_path = self.relative_path(atd.parent.parent)
                modules_with_tests.append(module_path)
                evidence.append(
                    Evidence(
                        file_path=self.relative_path(atd),
                        line_start=1,
                        line_end=1,
                        snippet=f"UI tests in {module_path}",
                    )
                )

        if modules_with_tests:
            return DetectionResult(
                detected=True,
                description=f"{len(modules_with_tests)} modules with androidTest",
                evidence=evidence,
            )

        return DetectionResult.not_found("No UI test locations found")


class TestFakesDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Test Fakes/Stubs Modules"

    @property
    def category(self) -> str:
        return "Test Infrastructure"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        fake_locations: list[str] = []

        patterns = ["fake", "stub", "mock", "test-double", "testcommon", "test-common"]

        settings = self.find_file("settings.gradle.kts", "settings.gradle")
        if settings:
            content = read_file_content(settings, root=self.repo_root) or ""
            modules = parse_include_modules(content)

            for module in modules:
                module_lower = module.lower()
                if any(p in module_lower for p in patterns):
                    fake_locations.append(module)
                    evidence.append(
                        Evidence(
                            file_path=self.relative_path(settings),
                            line_start=1,
                            line_end=1,
                            snippet=f"Test module: {module}",
                        )
                    )

        fake_class_matches = grep_files(
            self.repo_root,
            r"class\s+Fake\w+|class\s+Stub\w+|object\s+Fake\w+",
            "**/*.kt",
        )
        for m in fake_class_matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        if fake_locations or fake_class_matches:
            return DetectionResult(
                detected=True,
                description=(
                    f"{len(fake_locations)} test modules, {len(fake_class_matches)} fake classes"
                ),
                evidence=evidence,
            )

        return DetectionResult.not_found("No test fakes/stubs found")


def get_modules_detectors(repo_root: Path) -> list[BaseDetector]:
    return [
        FullModuleListDetector(repo_root),
        ModuleClassificationDetector(repo_root),
        ModuleDependencyGraphDetector(repo_root),
        ModuleGroupingDetector(repo_root),
        FlavorOverridesDetector(repo_root),
        UITestsLocationDetector(repo_root),
        TestFakesDetector(repo_root),
    ]
