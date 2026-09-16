# Starter contribution tasks

These are maintained candidate tasks for a first coador contribution. Before
starting, open or claim an issue so two people do not solve the same problem. A task
listed here is not assigned, promised for a release, or permission to broaden its
scope.

Every implementation must use synthetic fixtures or explicitly public pinned source.
Never attach a private Android checkout, generated private profile, credential or
internal URL. Read [`CONTRIBUTING.md`](../CONTRIBUTING.md) and
[`SECURITY.md`](../SECURITY.md) first.

## 1. Recognize GitHub Actions artifact uploads

**Outcome:** `artifacts_and_reports` recognizes a direct
`uses: actions/upload-artifact@...` step and reports its declared path as observed
repository evidence.

**Likely files:** `src/coador/detectors/ci_cd.py`, the synthetic workflow under
`tests/fixtures/mini_android/`, and a focused CI detector test.

**Acceptance:**

- Add positive YAML cases for a pinned and a major-version action reference.
- Add a negative case whose step name mentions an artifact but performs no upload.
- Assert the repository-relative evidence path and real source line, not only the
  summary.
- Keep output ordering deterministic and pass the full standard gate set.

**Not in scope:** resolving reusable workflows, querying a live CI run, verifying
that an uploaded artifact exists, or adding a YAML dependency.

## 2. Add PowerShell onboarding examples

**Outcome:** the pinned public-repository setup in `docs/onboarding-recipes.md` has a
tested PowerShell equivalent with explicit repository and external KB paths.

**Likely files:** `docs/onboarding-recipes.md` and
`tests/test_onboarding_recipes.py`.

**Acceptance:**

- Cover clone, detached checkout, heuristic scan and one focused `show` command.
- Include a path containing spaces and quote it correctly.
- Keep the POSIX instructions and all immutable revisions unchanged.
- State that package download uses the network while heuristic scanning does not.

**Not in scope:** adding a shell abstraction, changing CLI parsing, running Gradle or
claiming that every Windows shell behaves identically.

## 3. Add an opt-in public documentation link check

**Outcome:** a slow, network-enabled test verifies that pinned GitHub source links in
the README and onboarding recipes still resolve, while ordinary tests remain fully
offline.

**Likely files:** a new module under `tests/integration/`, the existing documentation
tests and pytest marker documentation if needed.

**Acceptance:**

- Extract only `github.com/.../blob/<40-character SHA>/...#L...` links from the two
  public documents.
- Fail on redirects to login/error pages and report the broken URL without dumping
  fetched source content.
- Reuse the existing `COADOR_INTEGRATION=1` opt-in boundary and set finite
  request timeouts.
- Keep default pytest free of network access and new runtime dependencies.

**Not in scope:** crawling arbitrary links, checking private repositories, mutating
GitHub state or turning network availability into a normal CI requirement.

## Proposing another small task

Use the detector coverage or documentation issue form. Define one observable
outcome, the smallest likely file set, positive and negative evidence, validation,
and exclusions. Changes to schema, persistence, security boundaries or Gradle
execution are not starter tasks and need design discussion first.
