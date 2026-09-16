# Architecture

## The shape of the thing

```
repository ──► scan ──► Profile ──┬──► profile.json ──► CLI, MCP server, search
                                  └──► layers/*.md      (for people and for review)
```

One scan produces one object. `profile.json` is what every interface reads;
the Markdown layers are a projection of the same object for human readers and
for code review. Nothing in the system parses generated Markdown back into data,
which is the mistake this design exists to avoid: a renderer change used to
silently break retrieval.

## Modules

| Module | Responsibility |
| --- | --- |
| `model.py` | `Profile` → `Layer` → `Section` → `Evidence`; JSON in and out; `SCHEMA_VERSION` |
| `registry.py` | The one table of layers and detectors: ids, titles, descriptions, keywords, kind |
| `repo.py`, `fileindex.py` | One walk of the tree, exclusion rules, glob matching, cached reads |
| `textscan.py` | Line and multiline search over the indexed files |
| `gradle.py`, `catalog.py`, `yaml_lite.py` | Heuristic parsing of build scripts, version catalogs and CI YAML |
| `redact.py` | Shared sanitization for source-derived public fields and public adapters |
| `detectors/` | 84 detectors in ten families, each answering one question with evidence |
| `gradle_probe.py`, `gradle_sections.py` | The optional pass that asks Gradle for ground truth |
| `scanner.py` | Runs the registry over a repository and assembles the `Profile` |
| `render/` | Markdown projection and atomic JSON writes |
| `search/` | BM25 over the sections, rebuilt from the profile on use |
| `kb.py` | `.coador/` layout, freshness, refresh policy, the read API |
| `cli.py`, `mcp_server.py` | Two thin adapters over `KnowledgeBase` |

## Decisions worth knowing

**No embeddings, no vector database.** After the evidence caps, the corpus is a
few thousand short strings, and the questions are identifier-shaped (`Hilt`,
`testInstrumentationRunner`, `productFlavors`) where exact matching beats
semantic similarity. BM25 over the profile answers in 60 ms with no model
download, no ONNX runtime and no server to run - which is also what makes the
MCP server start instantly. A vector retriever can be added later behind the
same interface; nothing in the model prevents it.

**Deterministic output.** No timestamps, no absolute paths and no set iteration
order reach a layer file, so two scans of the same tree are byte-identical. That
is what allows `.coador/` to be committed and reviewed like any other
generated artefact. Scan metadata that must vary (time, fingerprints, git
commit) lives in `manifest.json`.

**Signals, not interpretations.** A detector reports what it matched and where.
It will say "StateFlow and UiState types found", never "this project uses MVI".
The evidence is the product; the summary is a convenience.

**Two passes, one model.** Text matching is fast and needs nothing installed,
but it cannot see through convention plugins or flavours created in a loop.
Rather than guess, the heuristic pass reports "not found" and `--gradle` asks
the build. Every section records its `source`, so a reader can tell ground truth
from a guess.

**One walk.** Detectors used to re-glob the tree per pattern - 122 walks for one
scan, 50 seconds on a mid-size project. `FileIndex` walks once and caches file
text; the same scan now takes under four seconds.

**Two fingerprints.** A quick one over path, size and mtime answers "nothing
moved" without reading source bytes. Only when it differs is every file hashed
in full, so a fresh checkout or an `rsync` that rewrote timestamps does not
trigger a rescan. `status --verify-content` performs an explicit full check;
`scan --force` performs full verification and regeneration when metadata may
have been deliberately preserved.

The selected knowledge-base directory is removed from both discovery and
fingerprints, including a custom directory inside the repository. The same
dynamic exclusion is used by the shared file and directory index, so generated
output cannot become detector input.

## Provenance and output boundary

Schema v3 makes the strength of every evidence claim explicit. `source_lines`
has a repository-relative POSIX file path, a real one-based source range, and
the scanned snapshot's `source_line_count` and SHA-256 `source_digest`. The
count and digest validate that citation against captured text; they are not
freshness inputs. `file` identifies a repository-relative entry whose
`entry_type` is `file` or `directory`, with no lines. `gradle_model` identifies
a Gradle `project` and `property`, with neither source path nor lines. Renderers
and adapters present those forms without manufacturing a citation.

Inventory sections retain a stable ordered value list in memory and serialize each
value with all accepted supporting evidence. Deduplication therefore preserves
multiple locations. `inventory_completeness` is `complete`, `incomplete` or `unknown`;
bounded collectors also record `collection_limit` and, when stopped, a
`collection_stop_reason`. Evidence sampling affects the section-level evidence view,
not stored inventory values or their provenance. CLI and MCP section reads paginate
inventory records with deterministic decimal cursors; the persisted profile remains
the complete source of truth for everything actually collected.

`Profile.from_dict()` rejects every schema other than v3. The manifest has a
separate cache schema and records the tool, output-security and generation
contract versions, normalized scan options, requested/effective scan authority,
and Gradle fallback. Existing manifests without that contract are rejected and
normal refresh rebuilds them.

The manifest is the generation commit marker. It stores a digest of
`profile.json` and of every generated Markdown body; manual headers are outside
those digests. Refresh renders into a staging directory, atomically replaces
each artifact, and replaces the manifest last. Readers validate the committed
digest set, so they return one coherent generation or a controlled damaged-cache
error while publication is in progress. A cross-process advisory lock inside
the KB directory serializes writers. Process interruption is recoverable on the
next normal refresh; this is not a power-loss durability or hostile tamper
guarantee.

When only Markdown output is missing or damaged, refresh reconstructs it from a
valid committed profile without rerunning detectors and preserves every readable
manual header. `--refresh-header` is honored on an unchanged tree and rewrites
headers from the registry template without a source scan.

The selected repository root is the source trust boundary. Source references
are normalized as relative POSIX paths, and source symlinks, including internal
ones, are rejected during discovery, reading, fingerprinting and cached-profile
validation. POSIX reads open each component without following links. Windows
lacks the same component-opening primitive, so scanning there assumes a stable
tree. These checks are not an operating-system sandbox. An external
knowledge-base directory is an operational output boundary, not a source
reference.

Sanitization is deterministic and idempotent. It covers generated
source-derived snippets, summaries, inventory items and detector errors, as
well as direct model construction and the public JSON, CLI and MCP adapters. It
recognizes sensitive named properties; YAML and XML values; multiline and
escaped assignments; URL user info and sensitive query values; authorization
and cookie headers; private-key blocks; and common token-like values. It cannot
discover every secret or guarantee that private output is publishable.
Hand-authored Markdown headers before `<!-- GENERATED:BEGIN -->` are preserved
verbatim and are outside that generated-field boundary.

The manifest intentionally keeps sanitized legitimate local operational paths
(`repo_path` and, when available, `git_root`), alongside fingerprints and Git
metadata. CLI `status --json` exposes `repo_path`, `kb_dir` and `git_root`.
MCP `kb_status` exposes only the selected repository path, under `repository`;
it does not return the knowledge-base directory or Git root. These are
operational fields, not source evidence.

The Gradle pass remains explicitly opt-in. Its target build is arbitrary
configuration that may read available local data or make network requests, so
run it only for a trusted repository; source containment does not restrict it.

The snapshot digest is provenance metadata, not an authentication mechanism for
the cache. Generation digests detect accidental corruption, partial publication
and mixed files, but do not authenticate a cache against an actor that controls
both repository and KB directory. Normal freshness deliberately trusts unchanged
size and mtime; use `--force` when that metadata cannot be trusted.

The Gradle pass records both requested and effective authority. A failed probe is
stored as a heuristic fallback. A later heuristic scan that replaces a
Gradle-backed generation reports `gradle_to_heuristic` in CLI/MCP refresh output
and logs; Gradle is still never started without explicit opt-in.

## Adding a detector

1. Write the class in the right `detectors/` module. It gets `repo_root`, uses
   `grep_files`/`glob_files`, and returns a `DetectionResult` with `Evidence`.
2. Register it in `registry.py` with a stable `id`, a title, a one-sentence
   description and search keywords. Use `kind=ResultKind.INVENTORY` when the
   answer is a complete list rather than a sample.
3. Add the signal to `tests/fixtures/mini_android/` and a test asserting both
   the positive and the negative case.
4. Run `python -m coador.registry` to regenerate `docs/detectors.md`.

The registry is what makes a detector real: tables of contents, the catalogue
and search metadata are all generated from it, so a detector cannot be rendered
without being documented.

## Testing

`tests/fixtures/mini_android/` is a synthetic four-module Android project that
exercises every detector family: Hilt, Compose, Retrofit, Room, DataStore,
Navigation, Kaspresso with Kakao, MockWebServer, GitLab CI, GitHub Actions and
Marathon. It is deliberately small enough to read.

The Gradle pass is tested against a recorded model (`tests/data/`), so the suite
needs no JDK. Opt-in integration tests
(`COADOR_INTEGRATION=1 pytest -m slow`) clone a public Android project and
check both passes against it.
