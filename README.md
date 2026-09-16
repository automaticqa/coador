# Coador

**Give AI agents a map of your Android project before they start reading the code.**

Coador scans an Android repository locally and deterministically - without an LLM -
and builds a structured, evidence-backed knowledge base covering the project
architecture, Gradle configuration, test infrastructure, UI selectors, CI/CD, and
other high-value context.

Agents query that knowledge first, then inspect only the files required for the task.

**Faster context. Less repeated discovery. Lower token usage.**

Coador turns an Android repository into a local knowledge base that AI agents can
query instead of repeatedly re-reading and rediscovering the entire project.

The key idea behind Coador is simple: the scanning itself does not use AI or an LLM.

Coador deterministically analyzes an Android project, extracts the information most
useful for development and test automation, and stores it in a structured form:
architecture signals, Gradle configuration, modules and dependencies, test
infrastructure, UI selectors, deep links, CI/CD, test runners, fixtures,
dependency-injection overrides, and other project-level knowledge.

As a result, an AI agent does not need to rediscover a large repository from scratch
for every new task - searching for the right Gradle files, reconstructing the module
structure, identifying the test framework, or figuring out how UI tests are organized.

Instead, the agent can query an already prepared knowledge base and retrieve a compact
answer focused only on the part of the project it currently needs.

This reduces repeated repository discovery, lowers the amount of source code that has
to enter the model context, and reduces unnecessary token consumption.

## Why no AI in the scanner?

Coador deliberately separates fact extraction from AI interpretation.

The repository is scanned locally by specialized deterministic detectors. They do not
generate architectural descriptions and do not try to guess how the project is
designed. Coador records only signals that can be supported by source files, Gradle
configuration, or repository structure.

For example, instead of claiming:

> This project uses Clean Architecture.

Coador may report:

> `domain`, `data`, and `feature` modules were found, together with the observed
> dependencies between them.

The agent receives evidence rather than a pre-generated interpretation and can reason
about that evidence itself.

Whenever possible, Coador also preserves the provenance of each finding: the source
file and exact source lines, a file-level observation, or a value obtained from the
configured Gradle model.

## How it works

Coador scans an Android repository and builds a structured local profile of the
project. The analysis covers nine main areas:

| Layer | What it covers |
| --- | --- |
| Project overview | Repository identity, structure, applications and UI signals |
| Gradle and build | Build system, SDKs, variants, tasks and configuration |
| Architecture | DI, networking, persistence, navigation, state and concurrency |
| Modules | Module inventory, types and observed dependencies |
| Configuration | Environments, build config, resources, secrets and feature flags |
| Dependencies | Libraries and versions grouped by stack |
| Testing | Unit and instrumentation tests, runners, fixtures and test tasks |
| UI testing | Frameworks, screen objects, selectors, deep links and components |
| CI/CD | Pipelines, devices, reports, artifacts, retries and notifications |

The complete catalogue currently contains 84 detectors and is generated in
[docs/detectors.md](docs/detectors.md).

The resulting knowledge is stored locally and can be consumed both by developers and
by AI tools. Developers get a CLI and human-readable Markdown views. AI agents get an
MCP interface for reading the project overview, searching for information, and
retrieving individual sections with supporting evidence.

```text
Android repository
        ↓
Coador scan
        ↓
structured local knowledge base
        ↓
AI agent queries only the information it needs
        ↓
agent opens specific source files only when required
```

Coador produces two kinds of findings. A **signal** reports an observed capability
and samples its evidence. An **inventory** retains collected values such as deep
links, exported components and literal UI test selectors. Inventories declare whether
they are `complete`, `incomplete` or `unknown` within their documented collection
boundary.

The default scan reads repository text and needs no Android toolchain. An optional
`--gradle` pass asks a trusted project's configured build for facts that static text
cannot resolve, such as variants declared by convention plugins. Every section says
whether its source is `heuristic` or `gradle`.

## Practical example

Suppose an AI agent needs to add a new Android UI test.

Without Coador, the agent may first need to discover:

- where instrumentation tests are located;
- which test runner is used;
- whether a shared base test exists;
- how screen objects or robots are structured;
- whether the project uses Espresso, Kaspresso, or Compose testing;
- how authentication is handled in tests;
- which selectors already exist;
- whether test DI or fake dependencies are available;
- how the test is executed locally and in CI.

In a large repository, answering these questions can require inspecting dozens of
files before the actual task even begins.

With Coador, much of that information has already been collected and structured. The
agent can query only the test infrastructure, selectors, or CI configuration it needs
and then open a small number of specific source files required for the implementation.

For example, connect an agent to the recorded
[Now in Android revision](https://github.com/android/nowinandroid/tree/12f80da6518e161ed16a06a68e71fb8a873576d6)
and ask:

> **You:** How do I add and run an instrumentation UI test in this project?
>
> **Agent:** Put the test beside the existing app tests under
> [`app/src/androidTest`](https://github.com/android/nowinandroid/blob/12f80da6518e161ed16a06a68e71fb8a873576d6/app/src/androidTest/kotlin/com/google/samples/apps/nowinandroid/ui/NavigationTest.kt#L58-L80).
> Follow their Hilt/Compose setup: `@HiltAndroidTest`, `HiltAndroidRule` first,
> then `createAndroidComposeRule<MainActivity>()`. The app selects
> [`NiaTestRunner`](https://github.com/android/nowinandroid/blob/12f80da6518e161ed16a06a68e71fb8a873576d6/app/build.gradle.kts#L31-L39),
> which starts
> [`HiltTestApplication`](https://github.com/android/nowinandroid/blob/12f80da6518e161ed16a06a68e71fb8a873576d6/core/testing/src/main/kotlin/com/google/samples/apps/nowinandroid/core/testing/NiaTestRunner.kt#L17-L30).
> Shared fakes replace production bindings through
> [`@TestInstallIn`](https://github.com/android/nowinandroid/blob/12f80da6518e161ed16a06a68e71fb8a873576d6/core/data-test/src/main/kotlin/com/google/samples/apps/nowinandroid/core/data/test/TestDataModule.kt#L32-L51).
> CI runs the observed task
> [`./gradlew connectedDemoDebugAndroidTest`](https://github.com/android/nowinandroid/blob/12f80da6518e161ed16a06a68e71fb8a873576d6/.github/workflows/Build.yaml#L239-L247).
> That task is a source-backed reference, not a complete Gradle task enumeration.

The answer is compact, but each claim remains connected to evidence that the agent or
developer can inspect.

## Local and verifiable

By default, Coador works locally. Its standard analysis does not require:

- an LLM;
- an embedding model;
- a vector database;
- an external API;
- Docker;
- uploading repository source code to an external service.

The generated project profile is deterministic: the same repository state and scan
configuration are expected to produce the same structured result. This makes the
knowledge base suitable for keeping alongside the project, updating it with the
codebase, and reviewing its changes like any other generated project artifact.

`profile.json` is the machine-readable source of truth. Markdown layers are a human
projection of that profile. Exact source evidence contains repository-relative paths,
one-based ranges and a snapshot digest. File-level and Gradle-model findings use
their own provenance forms without fabricated line numbers.

Generated source-derived fields pass through shared sanitization for common secrets,
but sanitization is not a guarantee that private output is safe to publish. Review a
generated knowledge base before sharing it. The full trust boundary is documented in
[SECURITY.md](SECURITY.md).

Coador collects no telemetry from scanned projects. Its default scan does not access
the network. Package installation and the explicitly requested Gradle pass have their
own network and trust boundaries.

## Not a replacement for source code

Coador does not try to eliminate source-code inspection by AI agents. Its purpose is
to eliminate repeated broad repository discovery.

When an agent needs to modify a particular feature, it still opens the relevant
production and test files. What it no longer needs to do is repeatedly reconstruct
the overall architecture, test infrastructure, Gradle setup, and CI workflow from
scratch.

Coador acts as a pre-built map of the project: compact, structured, local, and backed
by source evidence.

The map has explicit limits:

- The default pass performs pattern matching rather than compilation. Missing
  heuristic evidence is not proof that a capability is absent.
- Convention plugins, generated build logic and dynamically created variants may
  require the optional Gradle pass.
- `coador scan --gradle` executes the target build's configuration and should be used
  only with a trusted project.
- Inventory completeness applies to the detector's documented source boundary, not
  to every value that could exist at runtime.
- The metadata freshness fast path cannot detect a content change whose path, size
  and modification time were deliberately preserved; use `--force` in that case.
- Coador complements symbol navigation, semantic search, build tools and device
  automation. It does not replace them.

## Installation

Coador requires Python 3.11 or newer. Release `0.1.0` is currently a release
candidate; after it is published, run it without a permanent installation through
`uvx`:

```bash
uvx --from coador==0.1.0 coador --version
```

To use the current checkout:

```bash
git clone https://github.com/automaticqa/coador.git
cd coador
uv sync --all-extras
uv run coador --version
```

An editable pip installation is also supported:

```bash
python -m pip install -e '.[dev]'
```

## CLI

The CLI exposes six commands:

| Command | Purpose |
| --- | --- |
| `scan` | Build or refresh the knowledge base |
| `status` | Report whether the stored knowledge is current |
| `layers` | List the nine knowledge layers |
| `overview` | Show a one-screen project map |
| `search` | Search sections with identifier-aware lexical ranking |
| `show` | Read one layer or section with its evidence |

Run the basic workflow from an Android repository:

```bash
coador scan
coador overview
coador search "where do the base URLs come from"
coador show 03_architecture di_framework
```

Every command supports `--json`. Use `--kb-dir` to keep generated output outside the
Android checkout. Use `coador scan --force` when source metadata cannot be trusted.
For a trusted project with a JDK and Gradle wrapper, `coador scan --gradle` adds the
configured Gradle model.

By default, generated knowledge lives here:

```text
.coador/
  .refresh.lock
  manifest.json
  profile.json
  layers/
```

The scanner reads Android source and build configuration without changing them. It
writes only to the selected knowledge-base directory and never edits the target
repository's `.gitignore`. The selected destination is excluded from scanning and
freshness fingerprints.

The `.coador/` directory is designed to be committed when a team wants the project
map reviewed and available without a local rescan. Hand-written Markdown above each
layer's `<!-- GENERATED:BEGIN -->` marker survives refreshes.

## MCP

`coador-mcp` serves one repository over MCP stdio with six `kb_*` tools and matching
`kb://` resources. Register an explicit Android repository so the server cannot
silently follow an unrelated working directory:

```bash
codex mcp add coador -- uvx --from coador==0.1.0 coador-mcp \
  --repo "/absolute/path/to/your/android/project"
codex mcp list
```

Open Codex in the Android project, use `/mcp` to verify the server, and ask a project
question. A useful first prompt is:

> How should I add an instrumentation test to this project? Identify the runner,
> application, observed test tasks, dependency overrides, helper or robot to extend,
> and useful selectors. Cite the repository evidence for each answer.

Configuration can also use `COADOR_REPO` and `COADOR_KB_DIR`. See
[docs/mcp.md](docs/mcp.md) for trusted project-scoped configuration, paths with
spaces, multiple repositories, Claude Code and other MCP clients.

## Examples

Start with the [local synthetic example](examples/README.md) to explore the current
profile schema without a network or Android toolchain. For the pinned Now in Android
walkthrough, generate the current CLI view outside the downloaded checkout:

```bash
git clone https://github.com/android/nowinandroid.git
git -C nowinandroid checkout 12f80da6518e161ed16a06a68e71fb8a873576d6
uvx --from coador==0.1.0 coador scan nowinandroid --kb-dir ../nowinandroid-coador
uvx --from coador==0.1.0 coador show 07_testing instrumentation_runner \
  nowinandroid --kb-dir ../nowinandroid-coador
uvx --from coador==0.1.0 coador show 07_testing test_tasks \
  nowinandroid --kb-dir ../nowinandroid-coador
```

The relevant output distinguishes evidence from limitations:

```console
$ coador show 07_testing instrumentation_runner nowinandroid --kb-dir ../nowinandroid-coador
Instrumentation Runner (instrumentation_runner)
Detected: Observed: runner: androidx.test.runner.AndroidJUnitRunner, com.google.samples.apps.nowinandroid.core.testing.NiaTestRunner
source: heuristic

  app/build.gradle.kts:38  testInstrumentationRunner = "com.google.samples.apps.nowinandroid.core.testing.NiaTestRunner"

  limitation: Static scanning cannot resolve runner configuration supplied only by convention plugins or generated build logic
```

The [evidence-first onboarding recipes](docs/onboarding-recipes.md) add walkthroughs
for CI instrumentation, launch targets and selectors, and Android Test Orchestrator
isolation across three pinned public repositories.

## Project status

Coador `0.1.0` is a release candidate and has not yet been published. The package
contains 84 detectors across nine layers, a local CLI, an MCP stdio server, optional
Gradle probing, deterministic JSON/Markdown output, evidence provenance, inventory
pagination, freshness checks and recovery from damaged generated output.

The configured CI matrix targets Linux on Python 3.11–3.13 and Windows/macOS on
Python 3.12. Network and real-project Gradle checks remain opt-in.

For development:

```bash
uv sync --all-extras
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
uv run python -m coador.registry --check
uv build
```

`COADOR_INTEGRATION=1 uv run pytest -m slow` additionally clones pinned public
Android repositories; the Gradle case requires a suitable Android/JDK toolchain.
Contributors can start with the
[starter contribution tasks](docs/contributor-tasks.md). Optional public usage
feedback follows the privacy boundaries in [docs/adoption.md](docs/adoption.md).

## License

MIT. See [LICENSE](LICENSE).
