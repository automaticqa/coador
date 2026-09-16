from __future__ import annotations

from pathlib import Path

from coador.catalog import load_catalog
from coador.detectors.base import BaseDetector, DetectionResult, Evidence
from coador.textscan import glob_files, grep_files, read_file_content


class VersionCatalogDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Versions Source-of-Truth"

    def detect(self) -> DetectionResult:
        catalog = load_catalog(self.repo_root)
        if catalog is not None:
            path = self.relative_path(catalog.path)
            evidence = [
                Evidence(
                    file_path=path,
                    line_start=1,
                    line_end=1,
                    snippet=(
                        f"{len(catalog.versions)} versions, {len(catalog.libraries)} libraries, "
                        f"{len(catalog.plugins)} plugins, {len(catalog.bundles)} bundles"
                    ),
                )
            ]
            evidence.extend(
                Evidence(file_path=path, line_start=1, line_end=1, snippet=f"{key} = {value}")
                for key, value in sorted(catalog.versions.items())
            )
            return DetectionResult(
                detected=True,
                description=f"Version catalog ({path}) with {len(catalog.versions)} versions",
                evidence=evidence,
            )

        properties = grep_files(
            self.repo_root,
            r"^\s*[\w.]*[Vv]ersion\s*=",
            ("gradle.properties", "buildSrc/**/*.kt", "buildSrc/**/*.gradle*"),
        )
        if properties:
            return DetectionResult(
                detected=True,
                description="Versions declared in properties or buildSrc, without a catalog",
                evidence=[
                    Evidence.from_match(
                        self.relative_path(m.file_path), m.line_number, m.line_content
                    )
                    for m in properties
                ],
            )

        return DetectionResult.not_found("No version catalog found")


class CoreStacksInventoryDetector(BaseDetector):
    # Keyword groups that place a dependency into a stack. Vendor names are listed
    # explicitly because that is what appears in a catalog alias or module name.
    CATEGORIES: dict[str, tuple[str, ...]] = {
        "Testing": (
            "junit",
            "mockk",
            "mockito",
            "kaspresso",
            "kakao",
            "espresso",
            "robolectric",
            "truth",
            "turbine",
            "mockwebserver",
            "wiremock",
            "ui-test",
            "uiautomator",
        ),
        "DI": ("dagger", "hilt", "koin", "kodein"),
        "Networking": ("retrofit", "okhttp", "ktor", "moshi", "gson", "apollo"),
        "Database": ("room", "datastore", "realm", "sqldelight", "objectbox"),
        "Analytics/Crash": ("analytics", "crashlytics", "sentry", "appcenter", "bugsnag"),
        "Marketing/Engagement": (
            "onesignal",
            "braze",
            "appsflyer",
            "adjust",
            "messaging",
            "exponea",
        ),
        "Content Platform": ("kontent", "kentico", "contentful", "strapi", "prismic"),
        "UI": ("compose", "material", "accompanist", "constraintlayout", "coil", "glide"),
    }

    @property
    def name(self) -> str:
        return "Core Stacks Inventory"

    def detect(self) -> DetectionResult:
        catalog = load_catalog(self.repo_root)
        if catalog is None or not catalog.libraries:
            return DetectionResult.not_found("No version catalog to inventory")

        path = self.relative_path(catalog.path)
        evidence: list[Evidence] = []
        summary: list[str] = []

        claimed: set[str] = set()
        for category, keywords in self.CATEGORIES.items():
            entries = [entry for entry in catalog.find(*keywords) if entry.alias not in claimed]
            if not entries:
                continue
            claimed.update(entry.alias for entry in entries)

            names = sorted({entry.module.partition(":")[2] or entry.alias for entry in entries})
            summary.append(f"{category}: {', '.join(names[:6])}")
            evidence.extend(
                Evidence(
                    file_path=path,
                    line_start=1,
                    line_end=1,
                    snippet=f"{category}: {entry.coordinates}",
                )
                for entry in sorted(entries, key=lambda item: item.alias)
            )

        if not summary:
            return DetectionResult.not_found("No known stacks found in the version catalog")

        return DetectionResult(detected=True, description="; ".join(summary), evidence=evidence)


class ComposeSetupDetector(BaseDetector):
    @property
    def name(self) -> str:
        return "Compose Setup"

    @property
    def category(self) -> str:
        return "UI Framework"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []

        libs_toml = self.find_file("gradle/libs.versions.toml")
        if libs_toml:
            content = read_file_content(libs_toml, root=self.repo_root) or ""

            if "compose" in content.lower():
                matches = grep_files(self.repo_root, r"compose", self.relative_path(libs_toml))
                for m in matches:
                    evidence.append(
                        Evidence.from_match(
                            self.relative_path(libs_toml), m.line_number, m.line_content
                        )
                    )

        compose_options = grep_files(
            self.repo_root, r"composeOptions|composeCompiler", "**/*.gradle*"
        )
        for m in compose_options:
            evidence.append(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
            )

        compose_files = grep_files(self.repo_root, r"@Composable", "**/*.kt")
        if compose_files:
            evidence.append(
                Evidence(
                    file_path=".",
                    line_start=1,
                    line_end=1,
                    snippet=f"Found {len(compose_files)}+ @Composable functions",
                )
            )

        if evidence:
            return DetectionResult(
                detected=True,
                description="Jetpack Compose",
                evidence=evidence,
            )

        return DetectionResult.not_found("No Compose setup found")


class QualityToolingDetector(BaseDetector):
    TOOLS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        ("Detekt", r"io\.gitlab\.arturbosch\.detekt|\bdetekt\b", ("**/detekt*.yml",)),
        ("Ktlint", r"org\.jlleitschuh\.gradle\.ktlint|\bktlint\b", (".editorconfig",)),
        ("Spotless", r"com\.diffplug\.spotless|\bspotless\b", ()),
        ("JaCoCo", r"\bjacoco\b", ()),
        ("Android Lint", r"lintOptions|\blint\s*\{", ("**/lint.xml",)),
        ("SonarQube", r"org\.sonarqube|sonar\.projectKey", ("sonar-project.properties",)),
    )

    @property
    def name(self) -> str:
        return "Quality Tooling"

    def detect(self) -> DetectionResult:
        evidence: list[Evidence] = []
        found: list[str] = []

        for tool, pattern, config_globs in self.TOOLS:
            matches = grep_files(
                self.repo_root,
                pattern,
                ("**/*.gradle", "**/*.gradle.kts", "gradle/libs.versions.toml"),
            )
            configs = glob_files(self.repo_root, config_globs) if config_globs else []
            if not matches and not configs:
                continue

            found.append(tool)
            evidence.extend(
                Evidence.from_match(self.relative_path(m.file_path), m.line_number, m.line_content)
                for m in matches
            )
            evidence.extend(
                Evidence(
                    file_path=self.relative_path(config),
                    line_start=1,
                    line_end=1,
                    snippet=f"{tool} configuration",
                )
                for config in configs
            )

        if found:
            return DetectionResult(detected=True, description=", ".join(found), evidence=evidence)

        return DetectionResult.not_found("No quality tooling found")


def get_dependencies_detectors(repo_root: Path) -> list[BaseDetector]:
    return [
        VersionCatalogDetector(repo_root),
        CoreStacksInventoryDetector(repo_root),
        ComposeSetupDetector(repo_root),
        QualityToolingDetector(repo_root),
    ]
