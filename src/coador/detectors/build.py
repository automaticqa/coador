from __future__ import annotations

import re
from pathlib import Path

from coador.catalog import load_catalog
from coador.detectors.base import BaseDetector, DetectionResult, Evidence
from coador.gradle import (
    extract_build_types,
    extract_flavor_names,
    parse_plugins,
)
from coador.textscan import glob_files, grep_files, read_file_content


class GradleEntryDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Gradle Entry Structure"

    @property
    def category(self) -> str:
        return "Build System"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        settings = self.find_file("settings.gradle.kts", "settings.gradle")
        if settings:
            content = read_file_content(settings, root=self.repo_root) or ""
            evidence.append(
                Evidence(
                    file_path=self.relative_path(settings),
                    line_start=1,
                    line_end=1,
                    snippet=f"Settings file: {settings.name}",
                )
            )

            if "pluginManagement" in content:
                matches = grep_files(self.repo_root, r"pluginManagement\s*\{", settings.name)
                for m in matches:
                    evidence.append(
                        Evidence.from_match(
                            self.relative_path(settings), m.line_number, m.line_content
                        )
                    )

            if "includeBuild" in content:
                matches = grep_files(self.repo_root, r"includeBuild", settings.name)
                for m in matches:
                    evidence.append(
                        Evidence.from_match(
                            self.relative_path(settings), m.line_number, m.line_content
                        )
                    )

        build_src = self.find_file("buildSrc")
        if build_src:
            evidence.append(
                Evidence(
                    file_path="buildSrc",
                    line_start=1,
                    line_end=1,
                    snippet="buildSrc directory present",
                )
            )

        if evidence:
            return DetectionResult(
                detected=True,
                description="Gradle build structure",
                evidence=evidence,
            )

        return DetectionResult.not_found("No Gradle structure found")


class BuildTypesDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Build Types / Flavors / Dimensions"

    @property
    def category(self) -> str:
        return "Build Variants"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        build_types: list[str] = []
        flavors: list[str] = []
        dimensions: list[str] = []

        build_files = glob_files(self.repo_root, "**/build.gradle.kts")
        build_files.extend(glob_files(self.repo_root, "**/build.gradle"))

        for bf in build_files:
            content = read_file_content(bf, root=self.repo_root) or ""

            extracted_types = extract_build_types(content)
            if extracted_types:
                build_types.extend(extracted_types)
                matches = grep_files(self.repo_root, r"buildTypes\s*\{", self.relative_path(bf))
                for m in matches:
                    evidence.append(
                        Evidence.from_match(self.relative_path(bf), m.line_number, m.line_content)
                    )

            extracted_flavors = extract_flavor_names(content)
            if extracted_flavors:
                flavors.extend(extracted_flavors)
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
                matches = grep_files(self.repo_root, r"flavorDimensions", self.relative_path(bf))
                for m in matches:
                    evidence.append(
                        Evidence.from_match(self.relative_path(bf), m.line_number, m.line_content)
                    )
                    dimensions.append(m.line_content)

        if evidence:
            desc_parts = []
            if build_types:
                desc_parts.append(f"buildTypes: {', '.join(sorted(set(build_types)))}")
            if flavors:
                desc_parts.append(f"flavors: {', '.join(sorted(set(flavors)))}")
            if dimensions:
                desc_parts.append("flavorDimensions: detected")
            return DetectionResult(
                detected=True,
                description="; ".join(desc_parts) if desc_parts else "Build variants configured",
                evidence=evidence,
            )

        return DetectionResult.not_found("No build types/flavors found")


class ModuleTypesDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Module Types"

    @property
    def category(self) -> str:
        return "Build Modules"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        counts = {"application": 0, "library": 0}

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
                counts["application"] += 1
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

            if "com.android.library" in resolved:
                counts["library"] += 1
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
                else:
                    evidence.append(
                        Evidence(
                            file_path=self.relative_path(bf),
                            line_start=1,
                            line_end=1,
                            snippet=f"Library: {module_path}",
                        )
                    )

        if any(counts.values()):
            desc = ", ".join(f"{k}: {v}" for k, v in counts.items() if v)
            return DetectionResult(
                detected=True,
                description=desc,
                evidence=evidence,
            )

        return DetectionResult.not_found("No module types detected")


class BuildTimeIntegrationsDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Build-time Integrations"

    @property
    def category(self) -> str:
        return "Build Integrations"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        features: list[str] = []

        patterns = [
            (r"minifyEnabled", "R8/Proguard"),
            (r"proguardFiles", "Proguard rules"),
            (r"shrinkResources", "Resource shrinker"),
            (r"dexguard|DexGuard", "DexGuard"),
            (r"composeOptions", "Compose compiler options"),
            (r"compose\s*=\s*true", "Compose buildFeatures"),
            (r"kotlinOptions", "Kotlin options"),
            (r"packagingOptions", "Packaging options"),
        ]

        for pattern, name in patterns:
            matches = grep_files(self.repo_root, pattern, "**/*.gradle*")
            if matches:
                features.append(name)
                for m in matches:
                    evidence.append(
                        Evidence.from_match(
                            self.relative_path(m.file_path), m.line_number, m.line_content
                        )
                    )

        if evidence:
            return DetectionResult(
                detected=True,
                description=", ".join(dict.fromkeys(features)),
                evidence=evidence,
            )

        return DetectionResult.not_found("No build-time integrations found")


class ConfigInjectionDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Config Injection Mechanisms"

    @property
    def category(self) -> str:
        return "Configuration"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        mechanisms: list[str] = []

        patterns = [
            (r"buildConfigField", "buildConfigField"),
            (r"resValue", "resValue"),
            (r"manifestPlaceholders", "manifestPlaceholders"),
        ]

        for pattern, name in patterns:
            matches = grep_files(self.repo_root, pattern, "**/*.gradle*")
            if matches:
                mechanisms.append(name)
                for m in matches:
                    evidence.append(
                        Evidence.from_match(
                            self.relative_path(m.file_path), m.line_number, m.line_content
                        )
                    )

        if evidence:
            return DetectionResult(
                detected=True,
                description=", ".join(mechanisms),
                evidence=evidence,
            )

        return DetectionResult.not_found("No config injection mechanisms found")


class VersionSourcesDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Version Sources"

    @property
    def category(self) -> str:
        return "Versioning"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        sources: list[str] = []

        libs_toml = self.find_file("gradle/libs.versions.toml")
        if libs_toml:
            sources.append("Version Catalog (libs.versions.toml)")
            evidence.append(
                Evidence(
                    file_path=self.relative_path(libs_toml),
                    line_start=1,
                    line_end=1,
                    snippet="Version Catalog",
                )
            )

        build_src = self.find_file("buildSrc")
        if build_src:
            sources.append("buildSrc")
            kt_files = self.glob("buildSrc/**/*.kt")
            for kf in kt_files:
                evidence.append(
                    Evidence(
                        file_path=self.relative_path(kf),
                        line_start=1,
                        line_end=1,
                        snippet=kf.name,
                    )
                )

        if evidence:
            return DetectionResult(
                detected=True,
                description=", ".join(sources),
                evidence=evidence,
            )

        return DetectionResult.not_found("No version sources found")


class CustomGradleLogicDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Custom Gradle Logic"

    @property
    def category(self) -> str:
        return "Build Customization"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        convention_plugins = glob_files(self.repo_root, "**/convention/**/*.gradle.kts")
        convention_plugins.extend(glob_files(self.repo_root, "**/convention/**/*.kt"))
        for cp in convention_plugins:
            evidence.append(
                Evidence(
                    file_path=self.relative_path(cp),
                    line_start=1,
                    line_end=1,
                    snippet=f"Convention plugin: {cp.name}",
                )
            )

        matches = grep_files(self.repo_root, r"tasks\.register", "**/*.gradle*")
        for m in matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        gradle_scripts = glob_files(self.repo_root, "**/gradle/*.gradle")
        gradle_scripts.extend(glob_files(self.repo_root, "**/gradle/*.gradle.kts"))
        for gs in gradle_scripts:
            evidence.append(
                Evidence(
                    file_path=self.relative_path(gs),
                    line_start=1,
                    line_end=1,
                    snippet=f"Gradle script: {gs.name}",
                )
            )

        if evidence:
            return DetectionResult(
                detected=True,
                description=f"{len(evidence)} custom gradle configurations",
                evidence=evidence,
            )

        return DetectionResult.not_found("No custom Gradle logic found")


class CodeGenerationDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Code/Resource Generation"

    @property
    def category(self) -> str:
        return "Code Generation"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        patterns = [
            r"tasks\.register.*[Gg]enerate",
            r"tasks\.register.*[Dd]ownload",
            r"tasks\.register.*[Ss]ync",
            r"kapt",
            r"ksp",
        ]

        for pattern in patterns:
            matches = grep_files(self.repo_root, pattern, "**/*.gradle*")
            for m in matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        if evidence:
            return DetectionResult(
                detected=True,
                description="Code generation tasks",
                evidence=evidence,
            )

        return DetectionResult.not_found("No code generation found")


class QualityGatesDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Quality Gates Config"

    @property
    def category(self) -> str:
        return "Quality"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        tools: list[str] = []

        patterns = [
            (r"lintOptions|lint\s*\{", "Android Lint"),
            (r"detekt", "Detekt"),
            (r"ktlint", "Ktlint"),
            (r"spotless", "Spotless"),
        ]

        for pattern, name in patterns:
            matches = grep_files(self.repo_root, pattern, "**/*.gradle*")
            if matches:
                tools.append(name)
                for m in matches:
                    evidence.append(
                        Evidence.from_match(
                            self.relative_path(m.file_path), m.line_number, m.line_content
                        )
                    )

        if evidence:
            return DetectionResult(
                detected=True,
                description=", ".join(tools),
                evidence=evidence,
            )

        return DetectionResult.not_found("No quality gates found")


def get_build_detectors(repo_root: Path) -> list[BaseDetector]:
    return [
        GradleEntryDetector(repo_root),
        ModuleTypesDetector(repo_root),
        BuildTypesDetector(repo_root),
        ConfigInjectionDetector(repo_root),
        VersionSourcesDetector(repo_root),
        CustomGradleLogicDetector(repo_root),
        CodeGenerationDetector(repo_root),
        BuildTimeIntegrationsDetector(repo_root),
        QualityGatesDetector(repo_root),
    ]
