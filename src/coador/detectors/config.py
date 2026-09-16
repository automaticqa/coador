from __future__ import annotations

from pathlib import Path

from coador.detectors.base import BaseDetector, DetectionResult, Evidence
from coador.detectors.build import ConfigInjectionDetector as BuildConfigInjectionDetector
from coador.textscan import glob_files, grep_files, read_file_content


class ConfigSourcesDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Config Sources Inventory"

    @property
    def category(self) -> str:
        return "Configuration"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        sources: list[str] = []

        patterns = [
            ("**/*.properties", "Properties files"),
            ("**/config*.json", "JSON configs"),
            ("**/config*.yaml", "YAML configs"),
            ("**/config*.yml", "YAML configs"),
            ("**/res/values/*.xml", "Values XML"),
        ]

        for pattern, name in patterns:
            files = glob_files(self.repo_root, pattern)
            if files:
                sources.append(f"{len(files)} {name}")
                for f in files:
                    evidence.append(
                        Evidence(
                            file_path=self.relative_path(f),
                            line_start=1,
                            line_end=1,
                            snippet=f.name,
                        )
                    )

        if evidence:
            return DetectionResult(
                detected=True,
                description=", ".join(sources),
                evidence=evidence,
            )

        return DetectionResult.not_found("No config sources found")


class EnvironmentMappingDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Environment Mapping"

    @property
    def category(self) -> str:
        return "Environments"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        envs: list[str] = []

        patterns = [
            (r"BASE_URL|baseUrl", "Base URLs"),
            (r"https?://[a-zA-Z0-9.-]+\.(dev|staging|prod)", "Environment URLs"),
            (r"environment|Environment", "Environment config"),
        ]

        for pattern, name in patterns:
            matches = grep_files(self.repo_root, pattern, "**/*.kt")
            if matches:
                envs.append(name)
                for m in matches:
                    evidence.append(
                        Evidence.from_match(
                            self.relative_path(m.file_path), m.line_number, m.line_content
                        )
                    )

        base_urls_files = glob_files(self.repo_root, "**/BaseUrls*.kt")
        for f in base_urls_files:
            evidence.append(
                Evidence(
                    file_path=self.relative_path(f),
                    line_start=1,
                    line_end=1,
                    snippet=f"Environment config: {f.name}",
                )
            )

        if evidence:
            return DetectionResult(
                detected=True,
                description=", ".join(envs) if envs else "Environment configuration",
                evidence=evidence,
            )

        return DetectionResult.not_found("No environment mapping found")


class SecretsHandlingDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Secrets Handling"

    @property
    def category(self) -> str:
        return "Security"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        gitignore = self.find_file(".gitignore")
        if gitignore:
            content = read_file_content(gitignore, root=self.repo_root) or ""
            secret_patterns = [
                "*.keystore",
                "*.jks",
                "secrets",
                "local.properties",
                "google-services.json",
            ]
            for pattern in secret_patterns:
                if pattern in content:
                    evidence.append(
                        Evidence(
                            file_path=self.relative_path(gitignore),
                            line_start=1,
                            line_end=1,
                            snippet=f"Ignored: {pattern}",
                        )
                    )

        example_files = glob_files(self.repo_root, "**/*.example")
        example_files.extend(glob_files(self.repo_root, "**/*.sample"))
        for f in example_files:
            evidence.append(
                Evidence(
                    file_path=self.relative_path(f),
                    line_start=1,
                    line_end=1,
                    snippet=f"Template: {f.name}",
                )
            )

        if evidence:
            return DetectionResult(
                detected=True,
                description="Secrets protection configured",
                evidence=evidence,
            )

        return DetectionResult.not_found("No secrets handling found")


class FeatureFlagsConfigDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Feature Flags / Remote Config Knobs"

    @property
    def category(self) -> str:
        return "Feature Flags"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        matches = grep_files(
            self.repo_root,
            r"featureFlag|FeatureFlag|featureToggle|FeatureToggle|RemoteConfig|remoteConfig|experimentId|experimentFlag|abTest|ABTest",
            "**/*.kt",
        )
        for m in matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        config_globs = [
            "**/config*.json",
            "**/config*.yml",
            "**/config*.yaml",
            "**/config*.properties",
            "**/config*.xml",
            "**/src/**/*.json",
            "**/src/**/*.yml",
            "**/src/**/*.yaml",
            "**/src/**/*.properties",
            "**/src/**/*.xml",
        ]
        for pattern in config_globs:
            config_matches = grep_files(
                self.repo_root,
                r"feature[_-]?flag|feature[_-]?toggle|remote[_-]?config|experiment",
                pattern,
            )
            for m in config_matches:
                evidence.append(
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                )

        if evidence:
            return DetectionResult(
                detected=True,
                description="Feature flags/remote config signals",
                evidence=evidence,
            )

        return DetectionResult.not_found("No feature flag config found")


class MarketingEngagementTogglesDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Marketing/Engagement Toggles"

    @property
    def category(self) -> str:
        return "Engagement"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        matches = grep_files(
            self.repo_root,
            r"(push|inapp|campaign|engagement|attribution).*(enable|disable|toggle)",
            "**/*.kt",
        )
        for m in matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        if evidence:
            return DetectionResult(
                detected=True,
                description="Marketing/engagement toggles",
                evidence=evidence,
            )

        return DetectionResult.not_found("No marketing/engagement toggles found")


class AnalyticsCrashTogglesDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Analytics/Crash Toggles"

    @property
    def category(self) -> str:
        return "Analytics"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        matches = grep_files(
            self.repo_root,
            r"(analytics|crashlytics|crash).*(enable|disable|collection|isEnabled)",
            "**/*.kt",
        )
        for m in matches:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        if evidence:
            return DetectionResult(
                detected=True,
                description="Analytics/crash toggles",
                evidence=evidence,
            )

        return DetectionResult.not_found("No analytics/crash toggles found")


class DebugToolingDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Debug Tooling Toggles"

    @property
    def category(self) -> str:
        return "Debug"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        tools: list[str] = []

        patterns = [
            (r"chucker|Chucker", "Chucker"),
            (r"stetho|Stetho", "Stetho"),
            (r"flipper|Flipper", "Flipper"),
            (r"leakcanary|LeakCanary", "LeakCanary"),
            (r"hyperion|Hyperion", "Hyperion"),
        ]

        for pattern, name in patterns:
            matches = grep_files(self.repo_root, pattern, "**/*.gradle*")
            if not matches:
                matches = grep_files(self.repo_root, pattern, "**/*.kt")
            if matches:
                tools.append(name)
                for m in matches:
                    evidence.append(
                        Evidence.from_match(
                            self.relative_path(m.file_path), m.line_number, m.line_content
                        )
                    )

        debug_dirs = glob_files(self.repo_root, "**/src/debug/**/*.kt")
        for f in debug_dirs:
            evidence.append(
                Evidence(
                    file_path=self.relative_path(f),
                    line_start=1,
                    line_end=1,
                    snippet=f"Debug source: {f.name}",
                )
            )

        if evidence:
            return DetectionResult(
                detected=True,
                description=", ".join(tools) if tools else "Debug tooling",
                evidence=evidence,
            )

        return DetectionResult.not_found("No debug tooling found")


def get_config_detectors(repo_root: Path) -> list[BaseDetector]:
    return [
        ConfigSourcesDetector(repo_root),
        BuildConfigInjectionDetector(repo_root),
        EnvironmentMappingDetector(repo_root),
        SecretsHandlingDetector(repo_root),
        FeatureFlagsConfigDetector(repo_root),
        MarketingEngagementTogglesDetector(repo_root),
        AnalyticsCrashTogglesDetector(repo_root),
        DebugToolingDetector(repo_root),
    ]
