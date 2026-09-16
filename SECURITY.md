# Security policy

## Supported versions

coador is preparing its first public release. Until a stable release is
published, security fixes apply to the latest commit on the repository's integration
branch. After release, the latest `0.1.x` version will be supported until this table
is updated.

| Version | Supported |
| --- | --- |
| latest `0.1.x` | Yes |
| older versions | No |

## Reporting a vulnerability

Do not include credentials, private repository content, generated private knowledge
bases or exploit details in a public issue.

After the public repository is available, use GitHub's private vulnerability
reporting under the repository's **Security** tab. Include the affected version,
platform, reproduction steps, impact and whether Gradle mode was enabled. If private
reporting is unavailable, open a public issue containing no sensitive details and
ask the maintainer for a private contact channel.

The maintainer will acknowledge a report, reproduce it where possible, assess the
affected versions and coordinate a fix and disclosure. No response-time guarantee is
made before a supported release exists.

## Security boundary

coador reads a selected Android repository and produces a structured profile,
Markdown projections and operational metadata. It is an orientation tool, not a
secret scanner, malware scanner, access-control system or operating-system sandbox.

### Default heuristic scan

The default scan reads repository files locally. It does not require a JDK, run
Gradle, download models or intentionally access the network.

Source discovery, reads and emitted references are constrained to the selected
repository root. Absolute, traversal, drive and UNC source references are rejected.
Source symlinks, including symlinks that still point inside the repository, are not
accepted. On POSIX, path components are opened without following links. Windows
does not provide the same implementation guarantee, so the repository tree must stay
stable during a scan.

These controls reduce accidental or malicious path escape through scanner input.
They do not restrict what the Python process, its dependencies, an MCP client or an
explicitly launched external tool can access with the user's operating-system
permissions.

### Output sanitization

Generated source-derived fields pass through a shared deterministic sanitization
boundary before a scanned profile is returned or persisted. Public CLI, MCP and
search adapters sanitize loaded data again. The policy recognizes supported forms
of named secret assignments, URL credentials and sensitive query values,
authorization and cookie headers, private-key blocks and common token-like values.

This is defense in depth, not exhaustive secret detection. Repository names, class
names, paths, identifiers, business terms and unsupported secret formats can remain
confidential even when snippets are removed. Always review `.coador/` before
committing or sharing output from a private repository.

Hand-written Markdown above `<!-- GENERATED:BEGIN -->` is preserved verbatim and is
not sanitized. A generated knowledge base is not authenticated: an actor who can
modify both the repository and its KB directory can also replace profiles and
manifest digests.

### Evidence and freshness

Only `source_lines` evidence claims an exact one-based range. It carries the scanned
snapshot's line count and digest. File-level evidence and Gradle-model facts do not
claim a source line. These provenance fields describe the captured scan; they are
not signatures or a substitute for source review.

Normal freshness first trusts path, size and modification time. A metadata change
causes a full-content fingerprint. Use `status --verify-content` or `scan --force`
when metadata may have been deliberately preserved. Generation digests and the
writer lock detect accidental corruption, incomplete publication and concurrent
writers, but are not cache authentication or a power-loss durability guarantee.

### Gradle mode

`coador scan --gradle` is explicit opt-in for a trusted target. A Gradle build
can execute arbitrary build logic with the user's permissions, read local files,
start processes and use the network. Scanner path containment does not sandbox
Gradle. MCP refresh never enables Gradle mode.

### MCP exposure

`coador-mcp` is a local stdio server launched with the user's permissions. The
selected repository is determined by `--repo`, `COADOR_REPO` or, as a fallback,
the server working directory. Persistent client configuration should use an explicit
repository path.

MCP tools and resources can expose profile summaries, inventory values, evidence
snippets and repository-relative source paths to the connected client. `kb_status`
also exposes the selected repository's sanitized local path and scan metadata. The
manifest retains operational paths such as `repo_path` and `git_root`; CLI
`status --json` additionally exposes `kb_dir`.

Read-only tool annotations describe intended side effects. They do not grant or deny
permission and do not override the MCP client's approval policy. `kb_refresh` writes
generated knowledge-base files and is marked non-read-only. Trusting a project-level
MCP configuration can launch its configured local command, so review that command
before trusting the project.

### Telemetry and adoption data

coador contains no analytics SDK, installation identifier, reporting endpoint or
background usage submission. CLI and MCP operations do not send repository content,
generated profiles, local paths, prompts or client transcripts to the project's
maintainers.

Feedback is voluntary and must not include private-project data or MCP-provider
logs. Package download, client provider behavior and network access by an explicitly
requested Gradle build remain separate trust boundaries.
See [`docs/adoption.md`](docs/adoption.md).

## Out of scope

- Protecting a machine after running an untrusted Gradle build or Python dependency.
- Guaranteeing that generated output is safe to publish.
- Detecting every credential, personal identifier, internal hostname or proprietary
  business term.
- Authenticating cached profiles against an attacker who controls their storage.
- Sandboxing the MCP client, model, repository hooks or other tools used alongside
  coador.

Reports about a concrete bypass of a documented path, sanitization, provenance or
adapter boundary are in scope even when the broader category above is not.
