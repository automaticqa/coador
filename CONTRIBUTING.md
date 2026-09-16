# Contributing

Thanks for taking a look. The project is small and the bar is simple: a change
should be honest about what it can detect, and provable by a test.

## Setup

```bash
uv sync --all-extras           # or: python -m pip install -e ".[dev]"
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
```

Python 3.11 or newer. The only runtime dependency is the MCP SDK.

## Adding or changing a detector

See [ARCHITECTURE.md](ARCHITECTURE.md#adding-a-detector). In short: implement it,
register it, extend `tests/fixtures/mini_android/` with the signal, and add a
test for both the positive and the negative case. Regenerate the catalogue with
`uv run python -m coador.registry`.

Two rules are worth stating explicitly:

- **Report signals, not conclusions.** "Found `@HiltAndroidApp` in `MiniApp.kt:8`"
  is a finding. "This project follows clean architecture" is not.
- **Never guess to look better.** If text matching cannot see the answer - as
  with flavours generated in `build-logic` - say "not found" and let the
  `--gradle` pass answer it.

## Output is a contract

Scan output must stay deterministic: no timestamps, no absolute paths, no
iteration over a `set` reaching a rendered string. `tests/test_kb.py` will catch
a regression, but it is easier not to write one.

Anything that could carry a secret goes through `redact.py` before it becomes
public output. The shared policy covers generated snippets, summaries,
inventories and detector errors, plus direct model and CLI/MCP adapter output.
Add a focused case to `tests/test_redact.py` for a supported form such as a
property, YAML or XML value, multiline or escaped assignment, URL credential or
query value, header, or private key. The policy is not a universal secret
detector or a publication guarantee.

Use explicit schema v3 provenance. Exact `source_lines` evidence must come from
the indexed snapshot, with a repository-relative POSIX file, valid one-based
range, source line count and digest. A `file` fact identifies a file or
directory and has no lines. A `gradle_model` fact identifies a Gradle project
and property and has no path or lines. Do not invent line numbers for either
non-source form. Inventory values keep item-level evidence and explicitly report
`complete`, `incomplete` or `unknown`; a collection cap must record its limit and
stop reason. The snapshot count and digest validate the citation only;
freshness continues to use manifest fingerprints.

Treat the selected repository root as a trust boundary. Do not introduce
absolute, traversal or link-based source references; symlinks, including
internal ones, are not source input. POSIX component-level no-follow reads and
a stable-tree assumption on Windows limit source access, but are not an OS
sandbox. `--gradle` remains opt-in for a trusted project because build
configuration can read locally and use the network.

Schema v1 and incompatible manifest contracts must remain rejected and rebuilt,
not silently upgraded. Keep the metadata quick path free of source reads; content
fingerprints must cover complete files when required. Any behavior-affecting
scan option belongs in the normalized manifest contract. Generated artifacts
must be staged, published under the writer lock and committed by replacing the
manifest last. Hand-authored Markdown headers before `<!-- GENERATED:BEGIN -->`
are preserved verbatim, excluded from generation digests and are not sanitized
generated fields.

Increment `OUTPUT_SECURITY_VERSION` when persisted output needs rebuilding under
a changed sanitization boundary, and `GENERATION_CONTRACT_VERSION` when artifact
validation or rendering compatibility changes. The persistent `.refresh.lock`
has fixed content; never delete it on unlock because that creates a second-inode
race between writers.

## Pull requests

Describe what the change detects and on which real project you saw it work.
A new detector that only fires on the fixture is a fair start, but say so.

For a bounded first contribution, see the maintained
[starter contribution tasks](docs/contributor-tasks.md). Before starting one, use
the detector-coverage or documentation issue form to claim it and confirm that its
scope is still current. Reproducible bugs have a separate structured form. Suspected
security vulnerabilities must follow [`SECURITY.md`](SECURITY.md), not a public
issue.

Experience reports are optional and use the `usage_feedback.yml` form. They never
require a private repository name, source, generated profile, path, prompt or MCP
transcript. Maintainers review this feedback under
[`docs/adoption.md`](docs/adoption.md).
