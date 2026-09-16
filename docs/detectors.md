# Detector catalogue

Generated from `src/coador/registry.py`; run `python -m coador.registry`
to refresh it. Every detector produces one section in the layer listed here,
whether or not the signal was found.

84 detectors across 9 layers.

## 01 Project Overview

`01_overview.md` - 6 detectors.

| Section id | Title | What it reports |
| --- | --- | --- |
| `repository_identity` | Repository Identity | The project name declared by rootProject.name in the Gradle settings script. |
| `brands_flavors_presence` | Brands / Flavors Presence | Whether the app ships several brands or variants: flavor dimensions, product flavours and application id suffixes. |
| `high_level_layout` | High-Level Layout | The top-level directories of the repository, as a first orientation to its shape. |
| `ui_technology_signals` | UI Technology Signals | Whether the UI is built with Jetpack Compose, XML layouts, or both. |
| `external_systems` | External Systems | Third-party platforms the app talks to: content platforms, push and attribution vendors, crash reporting and identity providers. |
| `documentation_locations` | Documentation Locations | Where the repository keeps its own documentation: README, CONTRIBUTING, docs and architecture decision records. |

## 02 Build and Run

`02_build_and_run.md` - 9 detectors.

| Section id | Title | What it reports |
| --- | --- | --- |
| `gradle_entry_structure` | Gradle Entry Structure | The Gradle entry points: settings script, plugin management, repository declarations and the wrapper. |
| `module_types` | Module Types | How many modules apply the Android application plugin versus the Android or JVM library plugins. |
| `build_types_flavors_dimensions` | Build Types / Flavors / Dimensions | The build types, product flavours and flavour dimensions declared in the build scripts. |
| `config_injection_mechanisms` | Config Injection Mechanisms | How configuration reaches the app at build time: buildConfigField, resValue and manifest placeholders. |
| `version_sources` | Version Sources | Where dependency versions are declared: a version catalog, buildSrc, or gradle.properties. |
| `custom_gradle_logic` | Custom Gradle Logic | Custom build logic: convention plugins, included builds and registered Gradle tasks. |
| `code_resource_generation` | Code/Resource Generation | Code and resource generation in the build: kapt, KSP, annotation processing and generator tasks. |
| `build_time_integrations` | Build-time Integrations | Build-time processing: R8 and ProGuard, resource shrinking, packaging options and Kotlin compiler options. |
| `quality_gates_config` | Quality Gates Config | Static analysis configured in the build scripts: Android Lint, Detekt, ktlint and Spotless. |

## 03 Architecture

`03_architecture.md` - 12 detectors.

> These are detected signals, not definitive architecture statements.

| Section id | Title | What it reports |
| --- | --- | --- |
| `layering_hints` | Layering Hints | How modules are grouped by their path prefix, as a hint at the intended layering. |
| `di_framework` | DI Framework | The dependency injection framework in use, and where components and modules are wired. |
| `networking_stack` | Networking Stack | The HTTP stack: client libraries, interceptors and the API declarations that use them. |
| `persistence` | Persistence | How data is stored on device: Room, DataStore, SharedPreferences and their declarations. |
| `navigation` | Navigation | How screens are connected: navigation libraries, navigation graphs and deep links. |
| `state_management` | State Management | How UI state is represented and observed: StateFlow, LiveData and UI state types. |
| `concurrency` | Concurrency | How asynchronous work is done: coroutines, dispatchers and flows. |
| `auth_session` | Auth/Session | How the app authenticates and keeps a session: tokens, refresh, OAuth and secure storage. |
| `content_platform_integration` | Content Platform Integration | Whether a headless content platform feeds the app. |
| `marketing_engagement` | Marketing/Engagement | Marketing and engagement SDKs: push messaging, campaigns and attribution. |
| `analytics_crash` | Analytics/Crash | Analytics and crash reporting SDKs wired into the app. |
| `feature_flags` | Feature Flags | Feature flag and remote configuration mechanisms. |

## 04 Modules Map

`04_modules_map.md` - 7 detectors.

| Section id | Title | What it reports |
| --- | --- | --- |
| `full_module_list` | Full Module List | Every Gradle module included by the settings script. |
| `module_classification` | Module Classification | Each module classified as an application, an Android library or a JVM library by the plugins it applies. |
| `module_dependency_graph` | Module Dependency Graph | Dependencies between modules, from project() declarations and type-safe project accessors. |
| `module_grouping` | Module Grouping | How module paths group into families such as feature, core or library. |
| `flavor_overrides_location` | Flavor Overrides Location | Flavour-specific source sets that override main sources. |
| `ui_tests_location_per_module` | UI Tests Location per Module | Which modules carry an androidTest source set, and where those tests live. |
| `test_fakes_stubs_modules` | Test Fakes/Stubs Modules | Modules and classes that provide fakes, stubs or mocks for tests. |

## 05 Config and Environment

`05_config_and_env.md` - 8 detectors.

| Section id | Title | What it reports |
| --- | --- | --- |
| `config_sources_inventory` | Config Sources Inventory | Configuration files carried by the repository: properties, JSON, YAML and XML resources. |
| `config_injection` | Config Injection | How configuration values reach the app: buildConfigField, resValue and manifest placeholders. |
| `environment_mapping` | Environment Mapping | Environments the app can point at, and the base URLs that define them. |
| `secrets_handling` | Secrets Handling | How secrets are kept out of the repository: ignored files, keystores and example templates. |
| `feature_flags_remote_config_knobs` | Feature Flags / Remote Config Knobs | Feature flag and remote configuration knobs exposed through configuration rather than code. |
| `marketing_engagement_toggles` | Marketing/Engagement Toggles | Configuration switches that enable or disable marketing and engagement features. |
| `analytics_crash_toggles` | Analytics/Crash Toggles | Configuration switches that control analytics and crash collection. |
| `debug_tooling_toggles` | Debug Tooling Toggles | Debug-only tooling wired into debug builds: network inspectors, leak detection and dev menus. |

## 06 Dependencies

`06_dependencies.md` - 4 detectors.

| Section id | Title | What it reports |
| --- | --- | --- |
| `versions_source_of_truth` | Versions Source-of-Truth | The parsed version catalog: how many versions, libraries, plugins and bundles it declares, and their values. |
| `core_stacks_inventory` | Core Stacks Inventory | The catalog libraries grouped into stacks: testing, DI, networking, database, analytics, marketing, content and UI. |
| `compose_setup` | Compose Setup | How Jetpack Compose is set up: catalog entries, compiler options and composable functions. |
| `quality_tooling` | Quality Tooling | Static analysis and coverage tooling declared for the project, with their configuration files. |

## 07 Testing

`07_testing.md` - 10 detectors.

| Section id | Title | What it reports |
| --- | --- | --- |
| `test_source_sets_map` | Test Source Sets Map | Which modules have unit test and instrumentation test source sets. |
| `non_ui_test_frameworks` | Non-UI Test Frameworks | Unit-test frameworks and assertion libraries in use. |
| `shared_fixtures_builders` | Shared Fixtures/Builders | Shared test fixtures, builders and test data helpers. |
| `test_resources` | Test Resources | Test resources and JSON fixtures used to stub responses and seed data. |
| `test_config_knobs` | Test Config Knobs | Test configuration in the build scripts: the instrumentation runner and testOptions. |
| `repo_docs_about_testing` | Repo Docs About Testing | Documentation the repository provides about its own testing. |
| `instrumentation_runner` | Instrumentation Runner | The runner that executes instrumentation tests, the Application it starts and whether the Android Test Orchestrator is used. |
| `test_tasks` | Test Tasks | The Gradle tasks that run the tests, including variant-specific tasks and Gradle managed devices. |
| `test_dependency_substitution` | Test Dependency Substitution | How production dependencies are replaced while tests run: Hilt test modules, fakes, and stubbed network servers. |
| `test_entry_points` | Test Entry Points | The base classes, JUnit rules and helper files a new test is expected to build on. |

## 08 UI Testing

`08_ui_testing.md` - 18 detectors.

| Section id | Title | What it reports |
| --- | --- | --- |
| `ui_test_framework_location` | UI Test Framework Location | Where instrumentation tests live and how their packages are organised. |
| `screen_objects_inventory` | Screen Objects Inventory | Screen and robot classes that wrap UI interaction for tests. |
| `screen_names_inventory` | Screen Names Inventory | The names of the screen classes defined for UI tests. |
| `ui_test_class_names` | UI Test Class Names | The instrumentation test classes present in the repository. |
| `ui_test_application_class` | UI Test Application Class | The Application class used by instrumentation tests and the DI framework behind it. |
| `scenarios_directory` | Scenarios Directory | A dedicated scenarios directory, as used by step-based UI test frameworks. |
| `compose_selectors_convention` | Compose Selectors Convention | How Compose nodes are made findable in tests: testTag and semantics conventions. |
| `kaspresso_framework` | Kaspresso Framework | Whether Kaspresso is used, and where its test cases and configuration live. |
| `step_dsl_helpers` | Step DSL / Helpers | The step DSL used by UI tests, including flakySafely and scenario helpers. |
| `synchronization_utilities` | Synchronization Utilities | How UI tests wait for the app: idling resources, wait helpers and timeouts. |
| `determinism_hooks` | Determinism Hooks | What makes UI tests deterministic: test DI components, fakes and stubbed network servers. |
| `login_auth_helpers` | Login/Auth Helpers | Helpers that log a user in or inject a session for UI tests. |
| `deep_links_webview_helpers` | Deep Links / WebView Helpers | Helpers for deep links and WebView flows in UI tests. |
| `ui_suite_grouping` | UI Suite Grouping | How UI tests are grouped into suites: annotations, tags and suite classes. |
| `reporting_hooks` | Reporting Hooks | Reporting hooks in test code: Allure annotations, screenshots and test watchers. |
| `deep_link_inventory` | Deep Link Inventory | Deep-link data declarations observed in source manifests, with item provenance and explicit merged-manifest limitations. |
| `exported_components` | Exported Components | Explicitly exported source-manifest components that other apps or test tooling may launch, without claiming merged-manifest truth. |
| `test_tag_inventory` | Test Tag Inventory | Literal Compose test tags and declared view ids available to UI tests, with collection completeness and item provenance. |

## 09 CI/CD

`09_ci_cd.md` - 10 detectors.

| Section id | Title | What it reports |
| --- | --- | --- |
| `ci_entrypoints` | CI Entrypoints | The CI configuration files that define the pipelines. |
| `jobs_and_stages` | Jobs & Stages | The stages and jobs declared by the CI configuration. |
| `scheduled_nightly_signals` | Scheduled/Nightly Signals | Whether pipelines run on a schedule, such as nightly regression runs. |
| `marathon_integration` | Marathon Integration | Whether the Marathon test runner is configured for device-farm style execution. |
| `variables_controlling_runs` | Variables Controlling Runs | CI variables that control what a run does: suite, flavour, emulator count, shards and retries. |
| `emulator_device_provisioning` | Emulator/Device Provisioning | How devices are provided in CI: runner tags, emulator images, KVM and AVD scripts. |
| `artifacts_and_reports` | Artifacts & Reports | What a pipeline keeps after a run: artifacts, JUnit reports and Allure results. |
| `notifications` | Notifications | Where pipeline results are announced: chat webhooks and e-mail. |
| `caching` | Caching | What CI caches between runs, such as the Gradle caches. |
| `retry_flakiness_handling` | Retry/Flakiness Handling | How the pipeline handles flaky runs: retries and retry strategies. |

