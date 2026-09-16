# Evidence-first Android onboarding recipes

These recipes turn common test-engineering questions into a small, repeatable
coador workflow. They use immutable revisions of public Android repositories,
so the expected findings can be checked without access to a private project.

For every repository, start with `status`, refresh only when needed, read the
overview, and then inspect focused sections. Treat commands found in source as
**observed commands**. Keep commands inferred from Gradle naming conventions as
**suggested commands** until the build confirms them.

## Prepare the public checkouts

The examples use POSIX temporary paths. Choose an equivalent external directory on
Windows. The default heuristic scan needs neither Gradle nor a JDK, but cloning the
examples uses the network.

```bash
git clone https://github.com/android/nowinandroid.git public/nowinandroid
git -C public/nowinandroid checkout 12f80da6518e161ed16a06a68e71fb8a873576d6

git clone https://github.com/android/architecture-samples.git public/architecture-samples
git -C public/architecture-samples checkout ee66e1526b84c026615df032c705842b7d2a521f

git clone https://github.com/android/testing-samples.git public/testing-samples
git -C public/testing-samples checkout 8c9df3a534ef99e44d481d96c00a5fc1970f7c70

coador scan public/nowinandroid --kb-dir /tmp/coador-recipes/nowinandroid
coador scan public/architecture-samples \
  --kb-dir /tmp/coador-recipes/architecture-samples
coador scan public/testing-samples/runner/AndroidTestOrchestratorSample \
  --kb-dir /tmp/coador-recipes/orchestrator-sample
```

`testing-samples` contains several independent Gradle builds. Selecting
`runner/AndroidTestOrchestratorSample` is intentional: always point coador at
the Android root whose tests you are onboarding, rather than an umbrella directory
that happens to contain several projects.

The CLI sequence maps directly to MCP:

| Step | CLI | MCP |
| --- | --- | --- |
| Check state | `status` | `kb_status` |
| Get the project passport | `overview` | `kb_overview` |
| Locate an unfamiliar topic | `search` | `kb_search` |
| Read one supported finding | `show` | `kb_get_section` |
| Refresh missing or stale output | `scan` | `kb_refresh` |

MCP refresh is heuristic. Use the CLI `scan --gradle` only when Gradle authority is
needed and the target build is trusted.

## Recipe 1: understand how instrumentation runs in CI

Question: **Which instrumentation task does CI run, how is its emulator prepared,
and where are its reports uploaded?**

```bash
coador show 07_testing test_tasks public/nowinandroid \
  --kb-dir /tmp/coador-recipes/nowinandroid
coador show 09_ci_cd emulator_device_provisioning public/nowinandroid \
  --kb-dir /tmp/coador-recipes/nowinandroid
coador show 09_ci_cd artifacts_and_reports public/nowinandroid \
  --kb-dir /tmp/coador-recipes/nowinandroid
```

Expected answer at the pinned revision:

- `connectedDemoDebugAndroidTest` is an observed task reference from the
  [Build workflow](https://github.com/android/nowinandroid/blob/12f80da6518e161ed16a06a68e71fb8a873576d6/.github/workflows/Build.yaml#L239-L247).
- The workflow prepares KVM before starting the emulator, also visible in the
  [same pinned source](https://github.com/android/nowinandroid/blob/12f80da6518e161ed16a06a68e71fb8a873576d6/.github/workflows/Build.yaml#L212-L217).
- `artifacts_and_reports` reports no observed CI upload or report pattern. Say that
  exactly; do not conclude that the live CI system retains nothing. Dynamic includes,
  external configuration and unrecognized actions are outside this static finding.

The task detector reports references, not a complete list of executable Gradle tasks.
If the exact runnable matrix matters, use trusted Gradle inspection and keep
its result separate from the heuristic evidence.

## Recipe 2: find launch targets and stable selectors

Question: **What can a black-box UI test launch directly, and which deep links or
literal selectors are available?**

```bash
coador show 08_ui_testing exported_components public/architecture-samples \
  --kb-dir /tmp/coador-recipes/architecture-samples
coador show 08_ui_testing deep_link_inventory public/architecture-samples \
  --kb-dir /tmp/coador-recipes/architecture-samples
coador show 08_ui_testing test_tag_inventory public/architecture-samples \
  --kb-dir /tmp/coador-recipes/architecture-samples
```

Expected answer at the pinned revision:

- The source manifest explicitly exports `TodoActivity`, backed by file-level
  evidence for
  [`app/src/main/AndroidManifest.xml`](https://github.com/android/architecture-samples/blob/ee66e1526b84c026615df032c705842b7d2a521f/app/src/main/AndroidManifest.xml#L26-L34).
- No source-manifest deep link is observed. Completeness is `unknown` because
  manifests are not merged and placeholders are not resolved.
- No literal Compose `testTag` or declared XML view ID is collected. That inventory
  is complete only within its stated literal-source boundary; runtime semantics,
  content descriptions and dynamically constructed selectors are not covered.

This recipe deliberately combines a positive finding with bounded negative ones.
Missing heuristic evidence is not proof of absence outside the documented source
boundary.

## Recipe 3: verify test-process isolation before extending a suite

Question: **Does each instrumentation test get an isolated process, which runner is
used, and what shared test setup should a new test extend?**

```bash
coador show 07_testing instrumentation_runner \
  public/testing-samples/runner/AndroidTestOrchestratorSample \
  --kb-dir /tmp/coador-recipes/orchestrator-sample
coador show 07_testing test_dependency_substitution \
  public/testing-samples/runner/AndroidTestOrchestratorSample \
  --kb-dir /tmp/coador-recipes/orchestrator-sample
coador show 07_testing test_entry_points \
  public/testing-samples/runner/AndroidTestOrchestratorSample \
  --kb-dir /tmp/coador-recipes/orchestrator-sample
```

Expected answer at the pinned revision:

- The configured runner is `AndroidJUnitRunner`, and
  `ANDROIDX_TEST_ORCHESTRATOR` is observed in the
  [app build file](https://github.com/android/testing-samples/blob/8c9df3a534ef99e44d481d96c00a5fc1970f7c70/runner/AndroidTestOrchestratorSample/app/build.gradle#L3-L35).
- The same build declares the Orchestrator test utility in its
  [test dependencies](https://github.com/android/testing-samples/blob/8c9df3a534ef99e44d481d96c00a5fc1970f7c70/runner/AndroidTestOrchestratorSample/app/build.gradle#L47-L54).
- No dependency substitution or shared entry point is observed. Do not translate
  that into “tests use production bindings” or “there is no helper”: unusual names
  and runtime wiring can escape static matching.

The scan sees managed-device configuration but does not enumerate its generated
tasks. Ask trusted Gradle for the exact task when execution, rather than orientation,
is the goal.

## Coverage and limits

The table describes supported evidence boundaries, not guaranteed findings in every
repository.

| Area | Useful layers and sections | What heuristic scanning can support | Boundary or next step |
| --- | --- | --- | --- |
| Repository orientation | `01_overview` | Identity, top-level layout, UI signals, docs and observed integrations | Signals do not establish product behavior or architectural intent. |
| Build and variants | `02_build_and_run` | Build scripts, plugins, declared build types, flavours and quality settings | Convention plugins and generated DSL can hide facts; trusted `scan --gradle` can override selected sections. |
| Architecture | `03_architecture` | Observable DI, networking, persistence, navigation, state and vendor-library patterns | No compilation, runtime graph or inferred label such as MVI. |
| Modules | `04_modules_map` | Included modules, text-declared module types/dependencies, test source sets and fakes | Dynamic includes and convention-plugin types can be incomplete; Gradle covers selected module facts. |
| Configuration and dependencies | `05_config_and_env`, `06_dependencies` | Configuration mechanisms, version catalogs and dependency stack signals | Not resolved dependency truth and not exhaustive secret discovery; generated output still needs review before sharing. |
| Test onboarding | `07_testing` | Runner, orchestrator, observed task references, frameworks, substitution and named helpers | Does not prove a task succeeds, a runtime DI graph, or that an unconventionally named helper is absent. |
| UI-test surface | `08_ui_testing` | Test locations, named robots/screens, literal tags/IDs, source-manifest deep links and exports | No merged manifest, resolved placeholders, runtime semantics or dynamic selector inventory. Read completeness per inventory. |
| CI execution | `09_ci_cd` | Recognized pipeline files, jobs, variables, devices, artifact/report patterns, caching and retries | Does not query live CI or resolve every include, reusable workflow, plugin or externally configured job. |

Across every area, exact line citations belong only to `source_lines` evidence.
File discoveries and Gradle-model properties have different provenance and must not
be presented with invented line numbers. Sanitization and path containment reduce
risk but do not make private generated output automatically safe to publish; see
[`SECURITY.md`](../SECURITY.md).
