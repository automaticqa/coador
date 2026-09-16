"""The registry of layers and detectors.

Every detector is declared once, here: its stable id (used by the CLI, the MCP
tools and ``profile.json``), the layer it belongs to, its human title and the
class that implements it. Table-of-contents entries and ``docs/detectors.md``
are generated from this table, so a detector can never be rendered without
being listed, or listed without being rendered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from coador.detectors import (
    architecture,
    build,
    ci_cd,
    config,
    dependencies,
    overview,
    test_runtime,
    testing,
    ui_testing,
)
from coador.detectors import modules as modules_detectors
from coador.detectors.base import BaseDetector
from coador.model import ResultKind


@dataclass(frozen=True)
class LayerSpec:
    """One Markdown layer of the knowledge base."""

    id: str
    title: str
    note: str | None = None

    @property
    def filename(self) -> str:
        return f"{self.id}.md"

    @property
    def heading(self) -> str:
        number = self.id.partition("_")[0]
        return f"{number} {self.title}"


@dataclass(frozen=True)
class DetectorSpec:
    """One detector and the section it produces."""

    id: str
    layer: str
    title: str
    detector_class: type[BaseDetector]
    description: str = ""
    keywords: tuple[str, ...] = field(default_factory=tuple)
    kind: ResultKind = ResultKind.SIGNAL

    def build(self, repo_root: Path) -> BaseDetector:
        return self.detector_class(repo_root)


LAYERS: tuple[LayerSpec, ...] = (
    LayerSpec(id="01_overview", title="Project Overview"),
    LayerSpec(id="02_build_and_run", title="Build and Run"),
    LayerSpec(
        id="03_architecture",
        title="Architecture",
        note="These are detected signals, not definitive architecture statements.",
    ),
    LayerSpec(id="04_modules_map", title="Modules Map"),
    LayerSpec(id="05_config_and_env", title="Config and Environment"),
    LayerSpec(id="06_dependencies", title="Dependencies"),
    LayerSpec(id="07_testing", title="Testing"),
    LayerSpec(id="08_ui_testing", title="UI Testing"),
    LayerSpec(id="09_ci_cd", title="CI/CD"),
)

_MODULE_BY_GROUP = {
    "overview": overview,
    "build": build,
    "architecture": architecture,
    "modules": modules_detectors,
    "config": config,
    "dependencies": dependencies,
    "testing": testing,
    "ui_testing": ui_testing,
    "ci_cd": ci_cd,
}

DETECTORS: tuple[DetectorSpec, ...] = (
    # 01_overview
    DetectorSpec(
        id="repository_identity",
        layer="01_overview",
        title="Repository Identity",
        detector_class=overview.RepositoryIdentityDetector,
        description=(
            "The project name declared by rootProject.name in the Gradle settings script."
        ),
        keywords=(
            "root project",
            "name",
            "settings.gradle",
            "rootProject",
        ),
    ),
    DetectorSpec(
        id="brands_flavors_presence",
        layer="01_overview",
        title="Brands / Flavors Presence",
        detector_class=overview.BrandsFlavorsDetector,
        description=(
            "Whether the app ships several brands or variants: flavor dimensions, product flavours "
            "and application id suffixes."
        ),
        keywords=(
            "brand",
            "white label",
            "flavor",
            "flavour",
            "dimension",
            "applicationIdSuffix",
            "variant",
        ),
    ),
    DetectorSpec(
        id="high_level_layout",
        layer="01_overview",
        title="High-Level Layout",
        detector_class=overview.HighLevelLayoutDetector,
        description=(
            "The top-level directories of the repository, as a first orientation to its shape."
        ),
        keywords=(
            "layout",
            "structure",
            "directories",
            "top level",
            "folders",
        ),
    ),
    DetectorSpec(
        id="ui_technology_signals",
        layer="01_overview",
        title="UI Technology Signals",
        detector_class=overview.UITechnologySignalsDetector,
        description=("Whether the UI is built with Jetpack Compose, XML layouts, or both."),
        keywords=(
            "compose",
            "jetpack compose",
            "xml layout",
            "view",
            "ui toolkit",
            "composable",
        ),
    ),
    DetectorSpec(
        id="external_systems",
        layer="01_overview",
        title="External Systems",
        detector_class=overview.ExternalSystemsDetector,
        description=(
            "Third-party platforms the app talks to: content platforms, push and attribution "
            "vendors, crash reporting and identity providers."
        ),
        keywords=(
            "integration",
            "vendor",
            "third party",
            "sdk",
            "push",
            "analytics",
            "auth provider",
        ),
    ),
    DetectorSpec(
        id="documentation_locations",
        layer="01_overview",
        title="Documentation Locations",
        detector_class=overview.DocumentationLocationsDetector,
        description=(
            "Where the repository keeps its own documentation: README, CONTRIBUTING, docs and "
            "architecture decision records."
        ),
        keywords=(
            "docs",
            "readme",
            "contributing",
            "adr",
            "documentation",
        ),
    ),
    # 02_build_and_run
    DetectorSpec(
        id="gradle_entry_structure",
        layer="02_build_and_run",
        title="Gradle Entry Structure",
        detector_class=build.GradleEntryDetector,
        description=(
            "The Gradle entry points: settings script, plugin management, repository declarations "
            "and the wrapper."
        ),
        keywords=(
            "gradle",
            "settings",
            "pluginManagement",
            "wrapper",
            "build script",
            "entry point",
        ),
    ),
    DetectorSpec(
        id="module_types",
        layer="02_build_and_run",
        title="Module Types",
        detector_class=build.ModuleTypesDetector,
        description=(
            "How many modules apply the Android application plugin versus the Android or JVM "
            "library plugins."
        ),
        keywords=(
            "module type",
            "application",
            "library",
            "plugin",
            "com.android.application",
        ),
    ),
    DetectorSpec(
        id="build_types_flavors_dimensions",
        layer="02_build_and_run",
        title="Build Types / Flavors / Dimensions",
        detector_class=build.BuildTypesDetector,
        description=(
            "The build types, product flavours and flavour dimensions declared in the build "
            "scripts."
        ),
        keywords=(
            "build type",
            "debug",
            "release",
            "flavor",
            "dimension",
            "variant",
        ),
    ),
    DetectorSpec(
        id="config_injection_mechanisms",
        layer="02_build_and_run",
        title="Config Injection Mechanisms",
        detector_class=build.ConfigInjectionDetector,
        description=(
            "How configuration reaches the app at build time: buildConfigField, resValue and "
            "manifest placeholders."
        ),
        keywords=(
            "buildConfigField",
            "resValue",
            "manifestPlaceholders",
            "config",
            "injection",
            "BuildConfig",
        ),
    ),
    DetectorSpec(
        id="version_sources",
        layer="02_build_and_run",
        title="Version Sources",
        detector_class=build.VersionSourcesDetector,
        description=(
            "Where dependency versions are declared: a version catalog, buildSrc, or "
            "gradle.properties."
        ),
        keywords=(
            "version",
            "catalog",
            "libs.versions.toml",
            "buildSrc",
            "gradle.properties",
        ),
    ),
    DetectorSpec(
        id="custom_gradle_logic",
        layer="02_build_and_run",
        title="Custom Gradle Logic",
        detector_class=build.CustomGradleLogicDetector,
        description=(
            "Custom build logic: convention plugins, included builds and registered Gradle tasks."
        ),
        keywords=(
            "convention plugin",
            "build-logic",
            "buildSrc",
            "task",
            "custom gradle",
        ),
    ),
    DetectorSpec(
        id="code_resource_generation",
        layer="02_build_and_run",
        title="Code/Resource Generation",
        detector_class=build.CodeGenerationDetector,
        description=(
            "Code and resource generation in the build: kapt, KSP, annotation processing and "
            "generator tasks."
        ),
        keywords=(
            "kapt",
            "ksp",
            "annotation processor",
            "codegen",
            "generate",
        ),
    ),
    DetectorSpec(
        id="build_time_integrations",
        layer="02_build_and_run",
        title="Build-time Integrations",
        detector_class=build.BuildTimeIntegrationsDetector,
        description=(
            "Build-time processing: R8 and ProGuard, resource shrinking, packaging options and "
            "Kotlin compiler options."
        ),
        keywords=(
            "minify",
            "proguard",
            "r8",
            "shrink",
            "packaging",
            "kotlinOptions",
        ),
    ),
    DetectorSpec(
        id="quality_gates_config",
        layer="02_build_and_run",
        title="Quality Gates Config",
        detector_class=build.QualityGatesDetector,
        description=(
            "Static analysis configured in the build scripts: Android Lint, Detekt, ktlint and "
            "Spotless."
        ),
        keywords=(
            "lint",
            "detekt",
            "ktlint",
            "spotless",
            "quality gate",
            "static analysis",
        ),
    ),
    # 03_architecture
    DetectorSpec(
        id="layering_hints",
        layer="03_architecture",
        title="Layering Hints",
        detector_class=architecture.LayeringHintsDetector,
        description=(
            "How modules are grouped by their path prefix, as a hint at the intended layering."
        ),
        keywords=(
            "layering",
            "grouping",
            "architecture",
            "modules",
            "feature",
            "core",
        ),
    ),
    DetectorSpec(
        id="di_framework",
        layer="03_architecture",
        title="DI Framework",
        detector_class=architecture.DIFrameworkDetector,
        description=(
            "The dependency injection framework in use, and where components and modules are wired."
        ),
        keywords=(
            "di",
            "dependency injection",
            "hilt",
            "dagger",
            "koin",
            "module",
            "inject",
            "component",
        ),
    ),
    DetectorSpec(
        id="networking_stack",
        layer="03_architecture",
        title="Networking Stack",
        detector_class=architecture.NetworkingStackDetector,
        description=(
            "The HTTP stack: client libraries, interceptors and the API declarations that use them."
        ),
        keywords=(
            "network",
            "http",
            "retrofit",
            "okhttp",
            "ktor",
            "interceptor",
            "api",
            "rest",
        ),
    ),
    DetectorSpec(
        id="persistence",
        layer="03_architecture",
        title="Persistence",
        detector_class=architecture.PersistenceDetector,
        description=(
            "How data is stored on device: Room, DataStore, SharedPreferences and their "
            "declarations."
        ),
        keywords=(
            "persistence",
            "database",
            "room",
            "datastore",
            "sharedpreferences",
            "cache",
            "storage",
        ),
    ),
    DetectorSpec(
        id="navigation",
        layer="03_architecture",
        title="Navigation",
        detector_class=architecture.NavigationDetector,
        description=(
            "How screens are connected: navigation libraries, navigation graphs and deep links."
        ),
        keywords=(
            "navigation",
            "navhost",
            "navcontroller",
            "deeplink",
            "graph",
            "route",
        ),
    ),
    DetectorSpec(
        id="state_management",
        layer="03_architecture",
        title="State Management",
        detector_class=architecture.StateManagementDetector,
        description=(
            "How UI state is represented and observed: StateFlow, LiveData and UI state types."
        ),
        keywords=(
            "state",
            "stateflow",
            "livedata",
            "uistate",
            "mvi",
            "mvvm",
            "viewmodel",
        ),
    ),
    DetectorSpec(
        id="concurrency",
        layer="03_architecture",
        title="Concurrency",
        detector_class=architecture.ConcurrencyDetector,
        description=("How asynchronous work is done: coroutines, dispatchers and flows."),
        keywords=(
            "concurrency",
            "coroutines",
            "dispatcher",
            "flow",
            "async",
            "suspend",
            "thread",
        ),
    ),
    DetectorSpec(
        id="auth_session",
        layer="03_architecture",
        title="Auth/Session",
        detector_class=architecture.AuthSessionDetector,
        description=(
            "How the app authenticates and keeps a session: tokens, refresh, OAuth and secure "
            "storage."
        ),
        keywords=(
            "auth",
            "login",
            "token",
            "refresh",
            "oauth",
            "session",
            "authorization",
            "jwt",
        ),
    ),
    DetectorSpec(
        id="content_platform_integration",
        layer="03_architecture",
        title="Content Platform Integration",
        detector_class=architecture.ContentPlatformDetector,
        description=("Whether a headless content platform feeds the app."),
        keywords=(
            "cms",
            "content",
            "headless",
            "kontent",
            "contentful",
        ),
    ),
    DetectorSpec(
        id="marketing_engagement",
        layer="03_architecture",
        title="Marketing/Engagement",
        detector_class=architecture.MarketingEngagementDetector,
        description=("Marketing and engagement SDKs: push messaging, campaigns and attribution."),
        keywords=(
            "marketing",
            "push",
            "campaign",
            "attribution",
            "engagement",
            "notification",
        ),
    ),
    DetectorSpec(
        id="analytics_crash",
        layer="03_architecture",
        title="Analytics/Crash",
        detector_class=architecture.AnalyticsCrashDetector,
        description=("Analytics and crash reporting SDKs wired into the app."),
        keywords=(
            "analytics",
            "crash",
            "crashlytics",
            "sentry",
            "tracking",
            "telemetry",
        ),
    ),
    DetectorSpec(
        id="feature_flags",
        layer="03_architecture",
        title="Feature Flags",
        detector_class=architecture.FeatureFlagsDetector,
        description=("Feature flag and remote configuration mechanisms."),
        keywords=(
            "feature flag",
            "toggle",
            "remote config",
            "experiment",
            "rollout",
        ),
    ),
    # 04_modules_map
    DetectorSpec(
        id="full_module_list",
        layer="04_modules_map",
        title="Full Module List",
        detector_class=modules_detectors.FullModuleListDetector,
        description=("Every Gradle module included by the settings script."),
        keywords=(
            "modules",
            "include",
            "settings.gradle",
            "module list",
            "subproject",
        ),
    ),
    DetectorSpec(
        id="module_classification",
        layer="04_modules_map",
        title="Module Classification",
        detector_class=modules_detectors.ModuleClassificationDetector,
        description=(
            "Each module classified as an application, an Android library or a JVM library by the "
            "plugins it applies."
        ),
        keywords=(
            "module",
            "classification",
            "application",
            "library",
            "type",
        ),
    ),
    DetectorSpec(
        id="module_dependency_graph",
        layer="04_modules_map",
        title="Module Dependency Graph",
        detector_class=modules_detectors.ModuleDependencyGraphDetector,
        description=(
            "Dependencies between modules, from project() declarations and type-safe project "
            "accessors."
        ),
        keywords=(
            "dependency graph",
            "module dependencies",
            "project()",
            "projects.",
            "edges",
        ),
    ),
    DetectorSpec(
        id="module_grouping",
        layer="04_modules_map",
        title="Module Grouping",
        detector_class=modules_detectors.ModuleGroupingDetector,
        description=("How module paths group into families such as feature, core or library."),
        keywords=(
            "grouping",
            "namespace",
            "feature",
            "core",
            "structure",
        ),
    ),
    DetectorSpec(
        id="flavor_overrides_location",
        layer="04_modules_map",
        title="Flavor Overrides Location",
        detector_class=modules_detectors.FlavorOverridesDetector,
        description=("Flavour-specific source sets that override main sources."),
        keywords=(
            "flavor source set",
            "override",
            "src",
            "variant sources",
        ),
    ),
    DetectorSpec(
        id="ui_tests_location_per_module",
        layer="04_modules_map",
        title="UI Tests Location per Module",
        detector_class=modules_detectors.UITestsLocationDetector,
        description=("Which modules carry an androidTest source set, and where those tests live."),
        keywords=(
            "androidTest",
            "instrumentation",
            "ui tests",
            "location",
            "module",
        ),
    ),
    DetectorSpec(
        id="test_fakes_stubs_modules",
        layer="04_modules_map",
        title="Test Fakes/Stubs Modules",
        detector_class=modules_detectors.TestFakesDetector,
        description=("Modules and classes that provide fakes, stubs or mocks for tests."),
        keywords=(
            "fake",
            "stub",
            "mock",
            "test double",
            "fixtures",
        ),
    ),
    # 05_config_and_env
    DetectorSpec(
        id="config_sources_inventory",
        layer="05_config_and_env",
        title="Config Sources Inventory",
        detector_class=config.ConfigSourcesDetector,
        description=(
            "Configuration files carried by the repository: properties, JSON, YAML and XML "
            "resources."
        ),
        keywords=(
            "config",
            "properties",
            "json",
            "yaml",
            "settings",
            "environment",
        ),
    ),
    DetectorSpec(
        id="config_injection",
        layer="05_config_and_env",
        title="Config Injection",
        detector_class=build.ConfigInjectionDetector,
        description=(
            "How configuration values reach the app: buildConfigField, resValue and manifest "
            "placeholders."
        ),
        keywords=(
            "buildConfigField",
            "resValue",
            "manifestPlaceholders",
            "config injection",
            "BuildConfig",
        ),
    ),
    DetectorSpec(
        id="environment_mapping",
        layer="05_config_and_env",
        title="Environment Mapping",
        detector_class=config.EnvironmentMappingDetector,
        description=("Environments the app can point at, and the base URLs that define them."),
        keywords=(
            "environment",
            "base url",
            "endpoint",
            "staging",
            "production",
            "dev",
        ),
    ),
    DetectorSpec(
        id="secrets_handling",
        layer="05_config_and_env",
        title="Secrets Handling",
        detector_class=config.SecretsHandlingDetector,
        description=(
            "How secrets are kept out of the repository: ignored files, keystores and example "
            "templates."
        ),
        keywords=(
            "secret",
            "keystore",
            "gitignore",
            "credentials",
            "signing",
            "properties",
        ),
    ),
    DetectorSpec(
        id="feature_flags_remote_config_knobs",
        layer="05_config_and_env",
        title="Feature Flags / Remote Config Knobs",
        detector_class=config.FeatureFlagsConfigDetector,
        description=(
            "Feature flag and remote configuration knobs exposed through configuration rather than "
            "code."
        ),
        keywords=(
            "feature flag",
            "toggle",
            "remote config",
            "knob",
            "experiment",
        ),
    ),
    DetectorSpec(
        id="marketing_engagement_toggles",
        layer="05_config_and_env",
        title="Marketing/Engagement Toggles",
        detector_class=config.MarketingEngagementTogglesDetector,
        description=(
            "Configuration switches that enable or disable marketing and engagement features."
        ),
        keywords=(
            "marketing toggle",
            "push enable",
            "campaign",
            "opt in",
            "consent",
        ),
    ),
    DetectorSpec(
        id="analytics_crash_toggles",
        layer="05_config_and_env",
        title="Analytics/Crash Toggles",
        detector_class=config.AnalyticsCrashTogglesDetector,
        description=("Configuration switches that control analytics and crash collection."),
        keywords=(
            "analytics toggle",
            "crash collection",
            "opt out",
            "tracking",
            "consent",
        ),
    ),
    DetectorSpec(
        id="debug_tooling_toggles",
        layer="05_config_and_env",
        title="Debug Tooling Toggles",
        detector_class=config.DebugToolingDetector,
        description=(
            "Debug-only tooling wired into debug builds: network inspectors, leak detection and "
            "dev menus."
        ),
        keywords=(
            "debug",
            "chucker",
            "stetho",
            "flipper",
            "leakcanary",
            "dev tools",
        ),
    ),
    # 06_dependencies
    DetectorSpec(
        id="versions_source_of_truth",
        layer="06_dependencies",
        title="Versions Source-of-Truth",
        detector_class=dependencies.VersionCatalogDetector,
        description=(
            "The parsed version catalog: how many versions, libraries, plugins and bundles it "
            "declares, and their values."
        ),
        keywords=(
            "version catalog",
            "libs.versions.toml",
            "versions",
            "dependency versions",
            "bom",
        ),
    ),
    DetectorSpec(
        id="core_stacks_inventory",
        layer="06_dependencies",
        title="Core Stacks Inventory",
        detector_class=dependencies.CoreStacksInventoryDetector,
        description=(
            "The catalog libraries grouped into stacks: testing, DI, networking, database, "
            "analytics, marketing, content and UI."
        ),
        keywords=(
            "dependencies",
            "libraries",
            "stack",
            "inventory",
            "catalog",
        ),
    ),
    DetectorSpec(
        id="compose_setup",
        layer="06_dependencies",
        title="Compose Setup",
        detector_class=dependencies.ComposeSetupDetector,
        description=(
            "How Jetpack Compose is set up: catalog entries, compiler options and composable "
            "functions."
        ),
        keywords=(
            "compose",
            "composable",
            "compose compiler",
            "bom",
            "material3",
        ),
    ),
    DetectorSpec(
        id="quality_tooling",
        layer="06_dependencies",
        title="Quality Tooling",
        detector_class=dependencies.QualityToolingDetector,
        description=(
            "Static analysis and coverage tooling declared for the project, with their "
            "configuration files."
        ),
        keywords=(
            "detekt",
            "ktlint",
            "spotless",
            "jacoco",
            "lint",
            "sonar",
            "coverage",
        ),
    ),
    # 07_testing
    DetectorSpec(
        id="test_source_sets_map",
        layer="07_testing",
        title="Test Source Sets Map",
        detector_class=testing.TestSourceSetsDetector,
        description=("Which modules have unit test and instrumentation test source sets."),
        keywords=(
            "test source set",
            "src/test",
            "androidTest",
            "unit tests",
            "modules",
        ),
    ),
    DetectorSpec(
        id="non_ui_test_frameworks",
        layer="07_testing",
        title="Non-UI Test Frameworks",
        detector_class=testing.NonUITestFrameworksDetector,
        description=("Unit-test frameworks and assertion libraries in use."),
        keywords=(
            "junit",
            "mockk",
            "mockito",
            "kotest",
            "truth",
            "turbine",
            "unit test",
        ),
    ),
    DetectorSpec(
        id="shared_fixtures_builders",
        layer="07_testing",
        title="Shared Fixtures/Builders",
        detector_class=testing.SharedFixturesDetector,
        description=("Shared test fixtures, builders and test data helpers."),
        keywords=(
            "fixture",
            "builder",
            "test data",
            "helper",
            "shared",
        ),
    ),
    DetectorSpec(
        id="test_resources",
        layer="07_testing",
        title="Test Resources",
        detector_class=testing.TestResourcesDetector,
        description=("Test resources and JSON fixtures used to stub responses and seed data."),
        keywords=(
            "test resources",
            "json",
            "fixtures",
            "assets",
            "stub data",
        ),
    ),
    DetectorSpec(
        id="test_config_knobs",
        layer="07_testing",
        title="Test Config Knobs",
        detector_class=testing.TestConfigKnobsDetector,
        description=(
            "Test configuration in the build scripts: the instrumentation runner and testOptions."
        ),
        keywords=(
            "testInstrumentationRunner",
            "testOptions",
            "orchestrator",
            "test configuration",
            "animations",
        ),
    ),
    DetectorSpec(
        id="repo_docs_about_testing",
        layer="07_testing",
        title="Repo Docs About Testing",
        detector_class=testing.TestDocsDetector,
        description=("Documentation the repository provides about its own testing."),
        keywords=(
            "testing docs",
            "readme",
            "how to test",
            "documentation",
        ),
    ),
    DetectorSpec(
        id="instrumentation_runner",
        layer="07_testing",
        title="Instrumentation Runner",
        detector_class=test_runtime.InstrumentationRunnerDetector,
        description=(
            "The runner that executes instrumentation tests, the Application it starts and "
            "whether the Android Test Orchestrator is used."
        ),
        keywords=(
            "runner",
            "testInstrumentationRunner",
            "AndroidJUnitRunner",
            "orchestrator",
            "HiltTestApplication",
            "how to run tests",
        ),
    ),
    DetectorSpec(
        id="test_tasks",
        layer="07_testing",
        title="Test Tasks",
        detector_class=test_runtime.TestTasksDetector,
        description=(
            "The Gradle tasks that run the tests, including variant-specific tasks and "
            "Gradle managed devices."
        ),
        keywords=(
            "gradle task",
            "connectedAndroidTest",
            "testDebugUnitTest",
            "managed devices",
            "run tests",
            "command",
        ),
    ),
    DetectorSpec(
        id="test_dependency_substitution",
        layer="07_testing",
        title="Test Dependency Substitution",
        detector_class=test_runtime.TestDependencySubstitutionDetector,
        description=(
            "How production dependencies are replaced while tests run: Hilt test modules, "
            "fakes, and stubbed network servers."
        ),
        keywords=(
            "TestInstallIn",
            "BindValue",
            "UninstallModules",
            "fake",
            "mockwebserver",
            "wiremock",
            "stub",
        ),
    ),
    DetectorSpec(
        id="test_entry_points",
        layer="07_testing",
        title="Test Entry Points",
        detector_class=test_runtime.TestEntryPointsDetector,
        description=(
            "The base classes, JUnit rules and helper files a new test is expected to build on."
        ),
        keywords=("base test", "TestCase", "rule", "TestWatcher", "robot", "helper", "start here"),
    ),
    # 08_ui_testing
    DetectorSpec(
        id="ui_test_framework_location",
        layer="08_ui_testing",
        title="UI Test Framework Location",
        detector_class=ui_testing.UITestFrameworkLocationDetector,
        description=("Where instrumentation tests live and how their packages are organised."),
        keywords=(
            "androidTest",
            "ui tests",
            "package",
            "location",
            "instrumentation",
        ),
    ),
    DetectorSpec(
        id="screen_objects_inventory",
        layer="08_ui_testing",
        title="Screen Objects Inventory",
        detector_class=ui_testing.ScreenObjectsInventoryDetector,
        description=("Screen and robot classes that wrap UI interaction for tests."),
        keywords=(
            "screen object",
            "page object",
            "robot",
            "kakao",
            "screen",
        ),
    ),
    DetectorSpec(
        id="screen_names_inventory",
        layer="08_ui_testing",
        title="Screen Names Inventory",
        detector_class=ui_testing.ScreenNamesInventoryDetector,
        description=("The names of the screen classes defined for UI tests."),
        keywords=(
            "screen names",
            "screens",
            "page objects",
            "inventory",
        ),
    ),
    DetectorSpec(
        id="ui_test_class_names",
        layer="08_ui_testing",
        title="UI Test Class Names",
        detector_class=ui_testing.UITestClassNamesDetector,
        description=("The instrumentation test classes present in the repository."),
        keywords=(
            "test classes",
            "ui tests",
            "test names",
            "androidTest",
        ),
    ),
    DetectorSpec(
        id="ui_test_application_class",
        layer="08_ui_testing",
        title="UI Test Application Class",
        detector_class=ui_testing.UITestApplicationDetector,
        description=(
            "The Application class used by instrumentation tests and the DI framework behind it."
        ),
        keywords=(
            "test application",
            "HiltTestApplication",
            "runner",
            "newApplication",
            "test di",
        ),
    ),
    DetectorSpec(
        id="scenarios_directory",
        layer="08_ui_testing",
        title="Scenarios Directory",
        detector_class=ui_testing.ScenariosDirectoryDetector,
        description=("A dedicated scenarios directory, as used by step-based UI test frameworks."),
        keywords=(
            "scenario",
            "kaspresso",
            "steps",
            "flows",
            "directory",
        ),
    ),
    DetectorSpec(
        id="compose_selectors_convention",
        layer="08_ui_testing",
        title="Compose Selectors Convention",
        detector_class=ui_testing.ComposeSelectorsDetector,
        description=(
            "How Compose nodes are made findable in tests: testTag and semantics conventions."
        ),
        keywords=(
            "testTag",
            "semantics",
            "compose test",
            "selector",
            "contentDescription",
        ),
    ),
    DetectorSpec(
        id="kaspresso_framework",
        layer="08_ui_testing",
        title="Kaspresso Framework",
        detector_class=ui_testing.KaspressoDetector,
        description=("Whether Kaspresso is used, and where its test cases and configuration live."),
        keywords=(
            "kaspresso",
            "kakao",
            "espresso",
            "ui test framework",
            "TestCase",
        ),
    ),
    DetectorSpec(
        id="step_dsl_helpers",
        layer="08_ui_testing",
        title="Step DSL / Helpers",
        detector_class=ui_testing.StepDSLDetector,
        description=("The step DSL used by UI tests, including flakySafely and scenario helpers."),
        keywords=(
            "step",
            "flakySafely",
            "dsl",
            "scenario",
            "kaspresso",
        ),
    ),
    DetectorSpec(
        id="synchronization_utilities",
        layer="08_ui_testing",
        title="Synchronization Utilities",
        detector_class=ui_testing.SynchronizationUtilitiesDetector,
        description=("How UI tests wait for the app: idling resources, wait helpers and timeouts."),
        keywords=(
            "idling resource",
            "wait",
            "synchronization",
            "timeout",
            "flaky",
            "await",
        ),
    ),
    DetectorSpec(
        id="determinism_hooks",
        layer="08_ui_testing",
        title="Determinism Hooks",
        detector_class=ui_testing.DeterminismHooksDetector,
        description=(
            "What makes UI tests deterministic: test DI components, fakes and stubbed network "
            "servers."
        ),
        keywords=(
            "mockwebserver",
            "wiremock",
            "fake",
            "TestInstallIn",
            "determinism",
            "stub",
        ),
    ),
    DetectorSpec(
        id="login_auth_helpers",
        layer="08_ui_testing",
        title="Login/Auth Helpers",
        detector_class=ui_testing.LoginAuthHelpersDetector,
        description=("Helpers that log a user in or inject a session for UI tests."),
        keywords=(
            "login helper",
            "auth",
            "token injection",
            "test user",
            "session",
        ),
    ),
    DetectorSpec(
        id="deep_links_webview_helpers",
        layer="08_ui_testing",
        title="Deep Links / WebView Helpers",
        detector_class=ui_testing.DeepLinksWebViewHelpersDetector,
        description=("Helpers for deep links and WebView flows in UI tests."),
        keywords=(
            "deep link",
            "webview",
            "intent",
            "uri",
            "helper",
        ),
    ),
    DetectorSpec(
        id="ui_suite_grouping",
        layer="08_ui_testing",
        title="UI Suite Grouping",
        detector_class=ui_testing.UISuiteGroupingDetector,
        description=("How UI tests are grouped into suites: annotations, tags and suite classes."),
        keywords=(
            "suite",
            "smoke",
            "regression",
            "tag",
            "annotation",
            "grouping",
        ),
    ),
    DetectorSpec(
        id="reporting_hooks",
        layer="08_ui_testing",
        title="Reporting Hooks",
        detector_class=ui_testing.ReportingHooksDetector,
        description=(
            "Reporting hooks in test code: Allure annotations, screenshots and test watchers."
        ),
        keywords=(
            "allure",
            "report",
            "screenshot",
            "artifact",
            "watcher",
        ),
    ),
    DetectorSpec(
        id="deep_link_inventory",
        layer="08_ui_testing",
        title="Deep Link Inventory",
        detector_class=test_runtime.DeepLinkInventoryDetector,
        description=(
            "Deep-link data declarations observed in source manifests, with item provenance "
            "and explicit merged-manifest limitations."
        ),
        keywords=("deep link", "intent filter", "scheme", "host", "uri", "entry point"),
        kind=ResultKind.INVENTORY,
    ),
    DetectorSpec(
        id="exported_components",
        layer="08_ui_testing",
        title="Exported Components",
        detector_class=test_runtime.ExportedComponentsDetector,
        description=(
            "Explicitly exported source-manifest components that other apps or test tooling "
            "may launch, without claiming merged-manifest truth."
        ),
        keywords=("exported", "activity", "service", "receiver", "provider", "launch", "manifest"),
        kind=ResultKind.INVENTORY,
    ),
    DetectorSpec(
        id="test_tag_inventory",
        layer="08_ui_testing",
        title="Test Tag Inventory",
        detector_class=test_runtime.TestTagInventoryDetector,
        description=(
            "Literal Compose test tags and declared view ids available to UI tests, with "
            "collection completeness and item provenance."
        ),
        keywords=("testTag", "android:id", "selector", "compose", "resource id", "locator"),
        kind=ResultKind.INVENTORY,
    ),
    # 09_ci_cd
    DetectorSpec(
        id="ci_entrypoints",
        layer="09_ci_cd",
        title="CI Entrypoints",
        detector_class=ci_cd.CIEntrypointsDetector,
        description=("The CI configuration files that define the pipelines."),
        keywords=(
            "ci",
            "gitlab",
            "github actions",
            "jenkins",
            "pipeline",
            "workflow",
        ),
    ),
    DetectorSpec(
        id="jobs_and_stages",
        layer="09_ci_cd",
        title="Jobs & Stages",
        detector_class=ci_cd.JobsStagesDetector,
        description=("The stages and jobs declared by the CI configuration."),
        keywords=(
            "stages",
            "jobs",
            "pipeline",
            "ci",
            "workflow",
        ),
    ),
    DetectorSpec(
        id="scheduled_nightly_signals",
        layer="09_ci_cd",
        title="Scheduled/Nightly Signals",
        detector_class=ci_cd.ScheduledSignalsDetector,
        description=("Whether pipelines run on a schedule, such as nightly regression runs."),
        keywords=(
            "schedule",
            "nightly",
            "cron",
            "trigger",
            "pipeline source",
        ),
    ),
    DetectorSpec(
        id="marathon_integration",
        layer="09_ci_cd",
        title="Marathon Integration",
        detector_class=ci_cd.MarathonIntegrationDetector,
        description=(
            "Whether the Marathon test runner is configured for device-farm style execution."
        ),
        keywords=(
            "marathon",
            "test runner",
            "sharding",
            "device farm",
        ),
    ),
    DetectorSpec(
        id="variables_controlling_runs",
        layer="09_ci_cd",
        title="Variables Controlling Runs",
        detector_class=ci_cd.VariablesControlDetector,
        description=(
            "CI variables that control what a run does: suite, flavour, emulator count, shards and "
            "retries."
        ),
        keywords=(
            "variable",
            "suite",
            "flavor",
            "emulator count",
            "shard",
            "retry",
            "parameter",
        ),
    ),
    DetectorSpec(
        id="emulator_device_provisioning",
        layer="09_ci_cd",
        title="Emulator/Device Provisioning",
        detector_class=ci_cd.EmulatorProvisioningDetector,
        description=(
            "How devices are provided in CI: runner tags, emulator images, KVM and AVD scripts."
        ),
        keywords=(
            "emulator",
            "avd",
            "kvm",
            "runner",
            "device",
            "image",
        ),
    ),
    DetectorSpec(
        id="artifacts_and_reports",
        layer="09_ci_cd",
        title="Artifacts & Reports",
        detector_class=ci_cd.ArtifactsReportsDetector,
        description=(
            "What a pipeline keeps after a run: artifacts, JUnit reports and Allure results."
        ),
        keywords=(
            "artifacts",
            "junit",
            "allure",
            "report",
            "results",
        ),
    ),
    DetectorSpec(
        id="notifications",
        layer="09_ci_cd",
        title="Notifications",
        detector_class=ci_cd.NotificationsDetector,
        description=("Where pipeline results are announced: chat webhooks and e-mail."),
        keywords=(
            "notification",
            "teams",
            "slack",
            "webhook",
            "alert",
        ),
    ),
    DetectorSpec(
        id="caching",
        layer="09_ci_cd",
        title="Caching",
        detector_class=ci_cd.CachingDetector,
        description=("What CI caches between runs, such as the Gradle caches."),
        keywords=(
            "cache",
            "gradle cache",
            "ci speed",
            "key",
            "policy",
        ),
    ),
    DetectorSpec(
        id="retry_flakiness_handling",
        layer="09_ci_cd",
        title="Retry/Flakiness Handling",
        detector_class=ci_cd.RetryFlakinessDetector,
        description=("How the pipeline handles flaky runs: retries and retry strategies."),
        keywords=(
            "retry",
            "flaky",
            "rerun",
            "stability",
            "strategy",
        ),
    ),
)


def layer_specs() -> tuple[LayerSpec, ...]:
    return LAYERS


def layer_spec(layer_id: str) -> LayerSpec | None:
    for spec in LAYERS:
        if spec.id == layer_id:
            return spec
    return None


def detectors_for(layer_id: str) -> tuple[DetectorSpec, ...]:
    return tuple(spec for spec in DETECTORS if spec.layer == layer_id)


def detector_spec(layer_id: str, detector_id: str) -> DetectorSpec | None:
    for spec in DETECTORS:
        if spec.layer == layer_id and spec.id == detector_id:
            return spec
    return None


def detector_catalog_markdown() -> str:
    """Render ``docs/detectors.md``: every layer with the detectors it contains."""
    lines = [
        "# Detector catalogue",
        "",
        "Generated from `src/coador/registry.py`; run `python -m coador.registry`",
        "to refresh it. Every detector produces one section in the layer listed here,",
        "whether or not the signal was found.",
        "",
        f"{len(DETECTORS)} detectors across {len(LAYERS)} layers.",
        "",
    ]

    for layer in LAYERS:
        specs = detectors_for(layer.id)
        lines.append(f"## {layer.heading}")
        lines.append("")
        lines.append(f"`{layer.filename}` - {len(specs)} detectors.")
        if layer.note:
            lines.append("")
            lines.append(f"> {layer.note}")
        lines.append("")
        lines.append("| Section id | Title | What it reports |")
        lines.append("| --- | --- | --- |")
        for spec in specs:
            lines.append(f"| `{spec.id}` | {spec.title} | {spec.description} |")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    """Write or verify ``docs/detectors.md``."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate the detector catalogue.")
    parser.add_argument("--output", default="docs/detectors.md", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero when the file on disk is out of date",
    )
    args = parser.parse_args()

    content = detector_catalog_markdown() + "\n"
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current != content:
            print(f"{args.output} is out of date; run: python -m coador.registry")
            return 1
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
