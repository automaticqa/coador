"""The MCP server: the knowledge base as tools an agent can call.

The server is a thin adapter over :class:`coador.kb.KnowledgeBase`. It holds
no state of its own beyond a lock, starts instantly because nothing heavy is
loaded at import time, and logs to stderr because stdout carries the protocol.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TypeVar, cast

import anyio
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from mcp.types import ToolAnnotations

from coador import __version__
from coador.kb import (
    DEFAULT_INVENTORY_PAGE_SIZE,
    KB_DIR_NAME,
    MAX_INVENTORY_PAGE_SIZE,
    KnowledgeBase,
    State,
)
from coador.model import Layer
from coador.redact import sanitize_public, sanitize_snippet
from coador.registry import LAYERS
from coador.repo import find_repo_root
from coador.scanner import DEFAULT_EVIDENCE_LIMIT

logger = logging.getLogger(__name__)

ENV_REPO = "COADOR_REPO"
ENV_KB_DIR = "COADOR_KB_DIR"

MAX_SEARCH_RESULTS = 50

T = TypeVar("T")


def _safe_dict(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], sanitize_public(value))


def _safe_list(value: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], sanitize_public(value))


INSTRUCTIONS = """\
This server describes one Android project: its build, architecture, modules,
configuration, dependencies, tests and CI, with explicit source-line, file-level
or Gradle-model provenance. Only source-line evidence provides exact line ranges.

Start with `kb_overview` - one screen that says what the project is. Then use
`kb_get_section` for the detail you need, or `kb_search` when you do not know
which section holds it. `kb_list_layers` shows what exists.

The answers come from a scan of the working tree, not from the model's
assumptions: prefer them over guessing, and quote the evidence paths when you
explain something. If `kb_status` reports the knowledge base as stale or
missing, call `kb_refresh` before relying on it.\
"""


def create_server(kb: KnowledgeBase) -> MCPServer:
    """Build the MCP server for one repository's knowledge base."""
    server = MCPServer(
        name="coador",
        version=__version__,
        instructions=INSTRUCTIONS,
    )
    refresh_lock = anyio.Lock()
    read_only = ToolAnnotations(read_only_hint=True, open_world_hint=False)

    @server.tool(
        description="Report whether the knowledge base exists and is current.",
        annotations=read_only,
    )
    def kb_status(verify_content: bool = False) -> dict[str, Any]:
        status = _guarded(lambda: kb.status(verify_content=verify_content))
        return _safe_dict(
            {
                "state": str(status.state),
                "summary": status.describe(),
                "repository": str(kb.repo_root),
                "scanned_at": status.scanned_at,
                "files_count": status.files_count,
                "git_commit": status.git_commit,
                "head_commit": status.head_commit,
                "changed_files_since_scan": status.changed_files,
                "needs_refresh": status.needs_refresh,
                "reason": status.reason,
                "scan_mode": status.scan_mode,
                "requested_scan_mode": status.requested_scan_mode,
                "gradle_fallback": status.gradle_fallback,
                "evidence_limit": status.evidence_limit,
            }
        )

    @server.tool(
        description=(
            "What kind of project this is: stack, variants, modules and testing, in one answer. "
            "Call this first."
        ),
        annotations=read_only,
    )
    def kb_overview() -> dict[str, Any]:
        return _safe_dict(_guarded(kb.overview))

    @server.tool(
        description="List the layers of the knowledge base and how much each one detected.",
        annotations=read_only,
    )
    def kb_list_layers() -> list[dict[str, Any]]:
        return _safe_list(_guarded(kb.list_layers))

    @server.tool(
        description=(
            "Read one section: what was detected, and the facts that prove it. Inventory "
            "items are paged; pass next_cursor back as cursor. Section ids come from "
            "kb_list_layers, kb_search or kb_overview."
        ),
        annotations=read_only,
    )
    def kb_get_section(
        layer_id: str,
        section_id: str,
        cursor: str | None = None,
        limit: int = DEFAULT_INVENTORY_PAGE_SIZE,
    ) -> dict[str, Any]:
        layer = _guarded(lambda: kb.get_layer(layer_id))
        if layer is None:
            known = ", ".join(spec.id for spec in LAYERS)
            raise ToolError(
                f"Unknown layer {sanitize_snippet(layer_id)!r}; available layers: {known}"
            )

        if layer.section(section_id) is None:
            known = ", ".join(item.id for item in layer.sections)
            raise ToolError(
                f"Unknown section {sanitize_snippet(section_id)!r} "
                f"in {sanitize_snippet(layer_id)}; "
                f"available: {known}"
            )

        capped = max(1, min(limit, MAX_INVENTORY_PAGE_SIZE))
        page = _guarded(
            lambda: kb.get_section_page(layer_id, section_id, cursor=cursor, limit=capped)
        )
        assert page is not None
        data = page.to_dict()
        data["layer"] = layer.id
        return _safe_dict(data)

    @server.tool(
        description=(
            "Search the knowledge base in plain language or by identifier "
            "(for example 'how are UI tests run', 'Hilt', 'testInstrumentationRunner')."
        ),
        annotations=read_only,
    )
    def kb_search(query: str, limit: int = 10, layer_id: str | None = None) -> list[dict[str, Any]]:
        capped = max(1, min(limit, MAX_SEARCH_RESULTS))
        hits = _guarded(lambda: kb.search(query, limit=capped, layer_id=layer_id))
        return _safe_list([hit.to_dict() for hit in hits])

    @server.tool(
        description=(
            "Rescan the repository. Only needed when kb_status reports the knowledge base "
            "as missing or stale; a scan of a large project takes a few seconds."
        ),
        annotations=ToolAnnotations(read_only_hint=False, idempotent_hint=True),
    )
    async def kb_refresh(
        context: Context[Any, Any],
        force: bool = False,
        evidence_limit: int = DEFAULT_EVIDENCE_LIMIT,
    ) -> dict[str, Any]:
        async with refresh_lock:
            logger.info("Scanning %s", sanitize_snippet(str(kb.repo_root)))
            progress = _ProgressReporter(context)
            try:
                status = await anyio.to_thread.run_sync(
                    lambda: kb.refresh(
                        force=force,
                        evidence_limit=evidence_limit or None,
                        on_progress=progress,
                    )
                )
            except Exception as exc:
                message = sanitize_snippet(str(exc)) or "Knowledge-base refresh failed"
                raise ToolError(message) from None
            return _safe_dict(
                {
                    "rescanned": status.refresh_action == "scanned",
                    "action": status.refresh_action,
                    "state": str(status.state),
                    "summary": status.describe(),
                    "files_count": status.files_count,
                    "scan_mode": status.scan_mode,
                    "requested_scan_mode": status.requested_scan_mode,
                    "gradle_fallback": status.gradle_fallback,
                    "authority_change": status.authority_change,
                }
            )

    @server.resource(
        "kb://layers",
        description="The layers of the knowledge base.",
        mime_type="application/json",
    )
    def layers_resource() -> list[dict[str, Any]]:
        return _safe_list(_guarded(kb.list_layers))

    @server.resource(
        "kb://layer/{layer_id}",
        description="One layer with all of its sections.",
        mime_type="application/json",
    )
    def layer_resource(layer_id: str) -> dict[str, Any]:
        layer = _guarded(lambda: kb.get_layer(layer_id))
        if layer is None:
            raise ResourceError(f"Unknown layer {sanitize_snippet(layer_id)!r}")
        return _safe_dict(Layer.from_dict(layer.to_dict()).to_dict())

    @server.resource(
        "kb://section/{layer_id}/{section_id}",
        description="One section with its evidence.",
        mime_type="application/json",
    )
    def section_resource(layer_id: str, section_id: str) -> dict[str, Any]:
        page = _guarded(
            lambda: kb.get_section_page(layer_id, section_id, limit=DEFAULT_INVENTORY_PAGE_SIZE)
        )
        if page is None:
            raise ResourceError(
                f"Unknown section {sanitize_snippet(layer_id)}/{sanitize_snippet(section_id)}"
            )
        return _safe_dict(page.to_dict())

    return server


class _ProgressReporter:
    """Forwards scan progress from the worker thread to the MCP client.

    Progress is best effort: there is no session when a tool is called in
    process, and a client that sent no progress token does not want it either.
    """

    def __init__(self, context: Context[Any, Any]) -> None:
        self._context = context
        self._enabled = True

    def __call__(self, done: int, total: int, label: str) -> None:
        if not self._enabled:
            return
        try:
            anyio.from_thread.run(
                self._context.report_progress, done, total, sanitize_snippet(label)
            )
        except Exception:
            logger.debug("Progress reporting is unavailable")
            self._enabled = False


def _guarded(read: Callable[[], T]) -> T:
    """Turn "no knowledge base yet" into an answer the agent can act on."""
    try:
        return read()
    except FileNotFoundError as exc:
        raise ToolError(f"{sanitize_snippet(str(exc))}. Call kb_refresh to build it.") from None
    except Exception as exc:
        raise ToolError(sanitize_snippet(str(exc)) or "Knowledge-base operation failed") from None


def resolve_knowledge_base(repo: str | None, kb_dir: str | None) -> KnowledgeBase:
    """Find the repository to serve: arguments first, then the environment, then the cwd."""
    raw = repo or os.environ.get(ENV_REPO) or "."
    start = Path(raw).expanduser().resolve()
    if not start.is_dir():
        raise SystemExit(f"Path does not exist: {sanitize_snippet(str(start))}")

    repo_root = find_repo_root(start)
    if repo_root is None:
        raise SystemExit(
            "No Gradle project found at "
            f"{sanitize_snippet(str(start))} (expected settings.gradle[.kts])"
        )

    raw_kb_dir = kb_dir or os.environ.get(ENV_KB_DIR)
    directory = Path(raw_kb_dir).expanduser().resolve() if raw_kb_dir else None
    try:
        return KnowledgeBase.for_repo(repo_root, directory)
    except ValueError as exc:
        raise SystemExit(
            f"Invalid knowledge-base directory: {sanitize_snippet(str(exc))}"
        ) from None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coador-mcp",
        description="Serve an Android project's knowledge base over MCP (stdio).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--repo",
        default=None,
        help=f"repository to serve (default: ${ENV_REPO} or the working directory)",
    )
    parser.add_argument(
        "--kb-dir",
        default=None,
        help=f"knowledge-base directory (default: ${ENV_KB_DIR} or <repo>/{KB_DIR_NAME})",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="enable debug logging on stderr"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    kb = resolve_knowledge_base(args.repo, args.kb_dir)
    status = kb.status()
    logger.info("Serving %s (%s)", sanitize_snippet(str(kb.repo_root)), status.state)
    if status.state is State.MISSING:
        logger.warning("No knowledge base yet; the agent can build one with kb_refresh")

    create_server(kb).run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
