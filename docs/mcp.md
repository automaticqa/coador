# Using coador from an agent

`coador-mcp` serves one repository's knowledge base over MCP (stdio). It
starts instantly, loads no models and its heuristic refresh does not open the
network. MCP refresh does not invoke the optional Gradle pass.

## Codex

Codex supports local stdio MCP servers. Give each Android project an explicit
repository path so the server cannot silently follow an unrelated launch working
directory:

```bash
codex mcp add coador-shop -- uvx --from coador==0.1.0 coador-mcp \
  --repo "/Users/me/Android Projects/shop"
codex mcp list
```

The shell quotes keep a path containing spaces in one argument. After opening
Codex in the Android project, use `/mcp` to verify that `coador-shop` is active
and exposes six `kb_*` tools. Registration makes the tools available; Codex still
applies the configured approval policy when it decides to invoke them.

`codex mcp add` writes the normal Codex configuration. To keep the server scoped
to one repository instead, create `.codex/config.toml` in the Android project:

```toml
[mcp_servers.coador]
command = "uvx"
args = [
  "--from",
  "coador==0.1.0",
  "coador-mcp",
  "--repo",
  "/Users/me/Android Projects/shop",
  "--kb-dir",
  "/Users/me/coador/shop",
]
cwd = "/Users/me/Android Projects/shop"
startup_timeout_sec = 10
tool_timeout_sec = 120
default_tools_approval_mode = "writes"
```

Codex loads project-scoped configuration only for a trusted project. Review the
command before trusting the checkout: an MCP command is a local process. The
`writes` policy allows the five read-only tools without a write prompt and keeps
`kb_refresh` subject to approval because it generates knowledge-base files.

For multiple Android projects, use a distinct server name and explicit `--repo`
for each one, such as `coador-shop` and `coador-payments`. Do not reuse a
single server whose repository is inferred from a shared working directory. The
optional `--kb-dir` keeps generated output outside a read-only checkout; it does
not change which repository is scanned.

These `uvx` examples describe the command for release `0.1.0` after it is published.
The first invocation can download the package and dependencies. Package download,
MCP server startup and Codex approval of a tool call are separate operations. Until
the release exists, contributors can install this checkout and invoke the installed
`coador-mcp` command directly.

[Official OpenAI Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp)
describes the current CLI, trusted project configuration and `/mcp` verification.

## Claude Code

```bash
# inside the Android project
claude mcp add coador -- uvx --from coador==0.1.0 coador-mcp --repo .
```

Or commit a `.mcp.json` next to the project so the whole team gets it:

```json
{
  "mcpServers": {
    "coador": {
      "command": "uvx",
      "args": ["--from", "coador==0.1.0", "coador-mcp", "--repo", "."],
      "env": {}
    }
  }
}
```

## Cursor, Windsurf, Gemini CLI and other MCP clients

The same command works anywhere an MCP stdio server can be declared:

```json
{
  "mcpServers": {
    "coador": {
      "command": "coador-mcp",
      "args": ["--repo", "/path/to/your/android/project"]
    }
  }
}
```

Configuration can also come from the environment: `COADOR_REPO` selects the
repository, `COADOR_KB_DIR` the knowledge-base directory. Without either, the
server looks for a Gradle project in the working directory. Prefer explicit paths
for persistent client configuration.

## What the agent gets

| Tool | Answers |
| --- | --- |
| `kb_overview` | What kind of project this is, in one call. Start here. |
| `kb_list_layers` | The nine layers and how much each one detected. |
| `kb_get_section` | One section with labelled provenance. Inventory items are paged and return `next_cursor`. |
| `kb_search` | Plain-language or identifier search across the knowledge base. |
| `kb_status` | Whether the knowledge base is current, and how far HEAD has moved. |
| `kb_refresh` | Rescan; only needed when `kb_status` says so. |

Resources mirror the same data for clients that prefer them: `kb://layers`,
`kb://layer/{layer_id}` and `kb://section/{layer_id}/{section_id}`.

Every tool except `kb_refresh` is marked read-only, so a client can distinguish
reads from the operation that writes generated knowledge-base files. Whether a
client prompts still depends on its approval policy.

## Evidence-first agent workflow

1. Call `kb_status`. If it reports `missing`, `stale` or `damaged`, request
   `kb_refresh` before relying on the knowledge base.
2. Call `kb_overview` for the project passport.
3. Use `kb_get_section` when the relevant section is known, or `kb_search` to find
   it. Follow `next_cursor` when an inventory has more pages.
4. Answer with the returned provenance. Cite exact lines only for `source_lines`;
   describe `file` and `gradle_model` evidence without inventing line numbers.
5. State an explicit limitation when the scan has no supported finding. Keep
   suggested commands separate from commands observed in repository evidence.

A useful first acceptance question is: "How should I add an instrumentation test
to this project? Identify the runner, application, task, dependency overrides and
helper or robot to extend, and cite the repository evidence for each answer."

`kb_status` returns the selected repository's sanitized local path in its
`repository` field, together with state and scan metadata. It does not expose a
knowledge-base directory or Git root. Those operational paths are retained in
the sanitized manifest (`repo_path`, and `git_root` when available), while CLI
`coador status --json` exposes `repo_path`, `kb_dir` and `git_root`.

Section evidence uses schema v3 provenance. `source_lines` has a
repository-relative POSIX file and a validated one-based range, with a source
snapshot line count and digest. `file` names a file or directory without lines.
`gradle_model` names a Gradle `project` and `property` without a source path or
lines. Snapshot fields validate an exact citation only; they do not drive
freshness. Clients must not turn file-level or Gradle-model facts into fictional
source lines. Inventory items each carry their own evidence and declare collection
completeness. `kb_get_section` returns 100 items by default, accepts `cursor` and
`limit`, and caps one MCP page at 200 items. The section resource returns the first
page; use the tool and its `next_cursor` for subsequent pages.

The server rejects incompatible profile and cache schemas. It validates the
profile and all generated layer bodies against the committed manifest before
serving them. `kb_status` reports `damaged` for incomplete or mixed output, and
`kb_refresh` repairs it through the normal lifecycle. MCP sanitizes source-derived
public values and adapter output for common properties, YAML/XML and multiline forms, escaped values, URL
credentials or sensitive query values, headers and private keys. This is not a
universal secret-discovery or publication guarantee. Manual Markdown headers
above `<!-- GENERATED:BEGIN -->` are user-owned and preserved unsanitized.

## Keeping it current

The knowledge base is committed to the repository, so a teammate who pulls gets
it without scanning. When the tree changes, `kb_status` reports `stale` and the
agent can call `kb_refresh` - a scan of a large project takes a few seconds.
Add `coador scan` to a pre-commit hook or a CI job if you would rather it
never drift.

Pass `verify_content=true` to `kb_status` for an explicit full-file check when
source metadata cannot be trusted. The default remains the lightweight metadata
path.

Normal refresh uses the fast metadata path and hashes complete files only after
metadata changes. MCP refresh stays heuristic. The manifest reports requested
and effective scan modes plus Gradle fallback; if MCP replaces stale Gradle-backed
output with heuristics, the response reports `gradle_to_heuristic`. Use the CLI
with `--gradle` when Gradle authority must be retained. Competing CLI/MCP writers
are serialized by the KB's filesystem lock.

## Trust boundary

Select a repository you trust with `--repo`, `COADOR_REPO`, or the working
directory used for discovery. Source references are relative POSIX paths below
that root; symlinks, including internal links, are rejected. POSIX uses
component-level no-follow opening, and Windows scanning assumes the tree stays
stable. This limits source access but is not an operating-system sandbox.

The separate CLI option `coador scan --gradle` executes arbitrary target
build configuration and can read available local data or use the network. It is
opt-in and should be used only for a trusted target.

See the repository [security policy](../SECURITY.md) for the complete scanner,
output, Gradle and MCP trust boundaries and vulnerability reporting guidance.
