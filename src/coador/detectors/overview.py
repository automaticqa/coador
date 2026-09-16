from __future__ import annotations

import re
from pathlib import Path

from coador.detectors.base import BaseDetector, DetectionResult, Evidence
from coador.gradle import (
    extract_flavor_names,
)
from coador.paths import UnsafePathError, checked_path
from coador.repo import is_excluded_dir
from coador.textscan import glob_files, grep_files, read_file_content


class RepositoryIdentityDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Repository Identity"

    @property
    def category(self) -> str:
        return "Overview"

    def detect(self) -> DetectionResult:
        settings = self.find_file("settings.gradle.kts", "settings.gradle")
        if not settings:
            return DetectionResult.not_found("settings.gradle not found")

        content = read_file_content(settings, root=self.repo_root) or ""
        match = re.search(r'rootProject\.name\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            line_matches = grep_files(
                self.repo_root,
                r"rootProject\.name",
                self.relative_path(settings),
            )
            evidence = []
            if line_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(settings),
                        line_matches[0].line_number,
                        line_matches[0].line_content,
                    )
                )
            else:
                evidence.append(
                    Evidence(
                        file_path=self.relative_path(settings),
                        line_start=1,
                        line_end=1,
                        snippet="rootProject.name found",
                    )
                )
            return DetectionResult(
                detected=True,
                description=f"rootProject.name = {match.group(1)}",
                evidence=evidence,
            )

        return DetectionResult(
            detected=True,
            description="settings.gradle found",
            evidence=[
                Evidence(
                    file_path=self.relative_path(settings),
                    line_start=1,
                    line_end=1,
                    snippet=f"Settings file: {settings.name}",
                )
            ],
        )


class BrandsFlavorsDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Brands / Flavors Presence"

    @property
    def category(self) -> str:
        return "Overview"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        flavor_names: list[str] = []
        flavor_dimensions: list[str] = []
        signals: list[str] = []

        build_files = glob_files(self.repo_root, "**/build.gradle.kts")
        build_files.extend(glob_files(self.repo_root, "**/build.gradle"))

        for bf in build_files:
            content = read_file_content(bf, root=self.repo_root) or ""
            if "productFlavors" in content:
                signals.append("productFlavors")
                names = extract_flavor_names(content)
                flavor_names.extend(names)
                matches = grep_files(
                    self.repo_root,
                    r"productFlavors\s*\{",
                    self.relative_path(bf),
                )
                for m in matches:
                    evidence.append(
                        Evidence.from_match(self.relative_path(bf), m.line_number, m.line_content)
                    )

            if "flavorDimensions" in content:
                signals.append("flavorDimensions")
                matches = grep_files(
                    self.repo_root,
                    r"flavorDimensions",
                    self.relative_path(bf),
                )
                for m in matches:
                    evidence.append(
                        Evidence.from_match(self.relative_path(bf), m.line_number, m.line_content)
                    )
                    flavor_dimensions.append(m.line_content)

            if "applicationIdSuffix" in content:
                signals.append("applicationIdSuffix")
                matches = grep_files(
                    self.repo_root,
                    r"applicationIdSuffix",
                    self.relative_path(bf),
                )
                for m in matches:
                    evidence.append(
                        Evidence.from_match(self.relative_path(bf), m.line_number, m.line_content)
                    )

            if "resConfigs" in content:
                signals.append("resConfigs")
                matches = grep_files(
                    self.repo_root,
                    r"resConfigs",
                    self.relative_path(bf),
                )
                for m in matches:
                    evidence.append(
                        Evidence.from_match(self.relative_path(bf), m.line_number, m.line_content)
                    )

        flavor_names = sorted(set(flavor_names))
        if flavor_names:
            signals.append(f"flavors: {', '.join(flavor_names)}")

        if evidence:
            return DetectionResult(
                detected=True,
                description=", ".join(dict.fromkeys(signals)),
                evidence=evidence,
            )

        return DetectionResult.not_found("No flavors or brands detected")


class HighLevelLayoutDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "High-Level Layout"

    @property
    def category(self) -> str:
        return "Overview"

    def detect(self) -> DetectionResult:
        top_dirs = []
        for candidate in self.repo_root.iterdir():
            try:
                child = checked_path(self.repo_root, candidate, directory=True)
            except UnsafePathError:
                continue
            if child.is_dir() and not is_excluded_dir(child.name):
                top_dirs.append(child.name)

        if not top_dirs:
            return DetectionResult.not_found("No top-level directories found")

        top_dirs = sorted(top_dirs)
        snippet = f"Top-level dirs: {', '.join(top_dirs)}"
        evidence = [
            Evidence(
                file_path=".",
                line_start=1,
                line_end=1,
                snippet=snippet,
            )
        ]

        return DetectionResult(
            detected=True,
            description=f"{len(top_dirs)} top-level directories",
            evidence=evidence,
        )


class UITechnologySignalsDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "UI Technology Signals"

    @property
    def category(self) -> str:
        return "Overview"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        signals: list[str] = []

        toml_path = self.find_file("gradle/libs.versions.toml")
        if toml_path:
            matches = grep_files(self.repo_root, r"compose", "gradle/libs.versions.toml")
            if matches:
                signals.append("Compose deps")
                for m in matches:
                    evidence.append(
                        Evidence.from_match(
                            self.relative_path(m.file_path), m.line_number, m.line_content
                        )
                    )

        composable_matches = grep_files(self.repo_root, r"@Composable", "**/*.kt")
        if composable_matches:
            signals.append("@Composable usage")
            for m in composable_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        xml_layouts = glob_files(self.repo_root, "**/res/layout/*.xml")
        if xml_layouts:
            signals.append("XML layouts")
            for xf in xml_layouts:
                evidence.append(
                    Evidence(
                        file_path=self.relative_path(xf),
                        line_start=1,
                        line_end=1,
                        snippet=xf.name,
                    )
                )

        if evidence:
            return DetectionResult(
                detected=True,
                description=", ".join(signals),
                evidence=evidence,
            )

        return DetectionResult.not_found("No UI technology signals found")


class ExternalSystemsDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "External Systems"

    @property
    def category(self) -> str:
        return "Overview"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        categories: dict[str, list[str]] = {}

        patterns = [
            ("Content platform", r"kontent|kentico|contentful"),
            (
                "Marketing/Engagement",
                r"onesignal|braze|appsflyer|adjust|firebase\.messaging|inapp|campaign|engagement",
            ),
            ("Analytics/Crash", r"firebase.*analytics|crashlytics|sentry|appcenter|bugsnag"),
            ("Auth", r"oauth|openid|appauth|auth0|jwt"),
        ]

        for label, pattern in patterns:
            matches = grep_files(self.repo_root, pattern, "**/*.gradle*")
            if not matches:
                matches = grep_files(self.repo_root, pattern, "**/*.kt")
            if matches:
                categories[label] = [pattern]
                for m in matches:
                    evidence.append(
                        Evidence.from_match(
                            self.relative_path(m.file_path), m.line_number, m.line_content
                        )
                    )

        if categories:
            description = ", ".join(sorted(categories.keys()))
            return DetectionResult(
                detected=True,
                description=description,
                evidence=evidence,
            )

        return DetectionResult.not_found("No external system signals found")


class DocumentationLocationsDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Documentation Locations"

    @property
    def category(self) -> str:
        return "Overview"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        readmes = glob_files(self.repo_root, "**/README*")
        for rf in readmes:
            evidence.append(
                Evidence(
                    file_path=self.relative_path(rf),
                    line_start=1,
                    line_end=1,
                    snippet=rf.name,
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

        docs_dirs = glob_files(self.repo_root, "**/docs/**/*")
        for df in docs_dirs:
            if df.is_file():
                evidence.append(
                    Evidence(
                        file_path=self.relative_path(df),
                        line_start=1,
                        line_end=1,
                        snippet=df.name,
                    )
                )

        adr_dirs = glob_files(self.repo_root, "**/adr/**/*")
        for af in adr_dirs:
            if af.is_file():
                evidence.append(
                    Evidence(
                        file_path=self.relative_path(af),
                        line_start=1,
                        line_end=1,
                        snippet=af.name,
                    )
                )

        if evidence:
            return DetectionResult(
                detected=True,
                description=f"{len(evidence)} documentation locations",
                evidence=evidence,
            )

        return DetectionResult.not_found("No documentation locations found")


def get_overview_detectors(repo_root: Path) -> list[BaseDetector]:
    return [
        RepositoryIdentityDetector(repo_root),
        BrandsFlavorsDetector(repo_root),
        HighLevelLayoutDetector(repo_root),
        UITechnologySignalsDetector(repo_root),
        ExternalSystemsDetector(repo_root),
        DocumentationLocationsDetector(repo_root),
    ]
