"""Command-line entry point for coador."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from coador import __version__
from coador.gradle_probe import DEFAULT_TIMEOUT_SECONDS as GRADLE_TIMEOUT_SECONDS
from coador.kb import DEFAULT_INVENTORY_PAGE_SIZE, KB_DIR_NAME, KnowledgeBase, State
from coador.model import Layer, Section, Source
from coador.redact import sanitize_public, sanitize_snippet
from coador.registry import LAYERS
from coador.repo import find_repo_root
from coador.scanner import DEFAULT_EVIDENCE_LIMIT

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coador",
        description="Build and query an evidence-backed knowledge base of an Android project.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="enable debug logging on stderr"
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    scan = subparsers.add_parser(
        "scan", help="scan an Android repository and (re)build its knowledge base"
    )
    _add_repo_arguments(scan)
    scan.add_argument("-f", "--force", action="store_true", help="rescan even when nothing changed")
    scan.add_argument(
        "--evidence-limit",
        type=int,
        default=DEFAULT_EVIDENCE_LIMIT,
        metavar="N",
        help=(
            "keep at most N evidence lines per section, 0 for no limit "
            f"(default: {DEFAULT_EVIDENCE_LIMIT}; the full count is always recorded)"
        ),
    )
    scan.add_argument(
        "--refresh-header",
        action="store_true",
        help="rewrite the hand-editable header of each layer from the built-in template",
    )
    scan.add_argument(
        "--gradle",
        action="store_true",
        help=(
            "ask Gradle for the module and variant model instead of guessing it "
            "(needs a JDK and the Gradle wrapper; slower)"
        ),
    )
    scan.add_argument(
        "--gradle-timeout",
        type=int,
        default=GRADLE_TIMEOUT_SECONDS,
        metavar="SECONDS",
        help=f"how long to wait for Gradle (default: {GRADLE_TIMEOUT_SECONDS})",
    )
    scan.add_argument(
        "--gradle-offline",
        action="store_true",
        help="run Gradle with --offline",
    )
    scan.add_argument("--json", action="store_true", help="print the result as JSON")
    scan.set_defaults(func=cmd_scan)

    status = subparsers.add_parser("status", help="report whether the knowledge base is current")
    _add_repo_arguments(status)
    status.add_argument(
        "--verify-content",
        action="store_true",
        help="hash complete source contents even when file metadata is unchanged",
    )
    status.add_argument("--json", action="store_true", help="print the status as JSON")
    status.set_defaults(func=cmd_status)

    layers = subparsers.add_parser("layers", help="list the layers of the knowledge base")
    _add_repo_arguments(layers)
    layers.add_argument("--json", action="store_true", help="print the layers as JSON")
    layers.set_defaults(func=cmd_layers)

    overview = subparsers.add_parser(
        "overview", help='one-screen answer to "what kind of project is this"'
    )
    _add_repo_arguments(overview)
    overview.add_argument("--json", action="store_true", help="print the overview as JSON")
    overview.set_defaults(func=cmd_overview)

    find = subparsers.add_parser("search", help="search the knowledge base")
    find.add_argument("query", metavar="QUERY")
    _add_repo_arguments(find)
    find.add_argument(
        "--layer", default=None, metavar="LAYER", help="restrict the search to one layer"
    )
    find.add_argument("--limit", type=int, default=10, metavar="N", help="how many hits to show")
    find.add_argument("--json", action="store_true", help="print the hits as JSON")
    find.set_defaults(func=cmd_search)

    show = subparsers.add_parser("show", help="show one layer or one section")
    show.add_argument("layer", choices=[spec.id for spec in LAYERS], metavar="LAYER")
    show.add_argument("section", nargs="?", default=None, metavar="SECTION")
    _add_repo_arguments(show)
    show.add_argument(
        "--cursor",
        default=None,
        metavar="CURSOR",
        help="continue an inventory page from this cursor",
    )
    show.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_INVENTORY_PAGE_SIZE,
        metavar="N",
        help=(f"inventory items per page, 0 for all (default: {DEFAULT_INVENTORY_PAGE_SIZE})"),
    )
    show.add_argument("--json", action="store_true", help="print the content as JSON")
    show.set_defaults(func=cmd_show)

    subparsers.add_parser("mcp", help="serve an Android repository over MCP stdio")

    return parser


def _add_repo_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="repository root (default: locate a Gradle settings file under the current directory)",
    )
    parser.add_argument(
        "--kb-dir",
        default=None,
        metavar="DIR",
        help=f"knowledge-base directory (default: <repo>/{KB_DIR_NAME})",
    )


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def open_kb(args: argparse.Namespace) -> KnowledgeBase | None:
    """Resolve the repository and return its knowledge base, or None when not found."""
    start = Path(args.path).expanduser().resolve() if args.path else Path.cwd()
    if not start.is_dir():
        logger.error("Path does not exist: %s", sanitize_snippet(str(start)))
        return None

    repo_root = find_repo_root(start)
    if repo_root is None:
        logger.error(
            "No Gradle project found at %s (expected settings.gradle[.kts])",
            sanitize_snippet(str(start)),
        )
        return None

    kb_dir = Path(args.kb_dir).expanduser().resolve() if args.kb_dir else None
    try:
        return KnowledgeBase.for_repo(repo_root, kb_dir)
    except ValueError as exc:
        logger.error("Invalid knowledge-base directory: %s", sanitize_snippet(str(exc)))
        return None


def emit(data: Any, as_json: bool, text: str) -> None:
    safe_data = sanitize_public(data)
    print(
        json.dumps(safe_data, indent=2, ensure_ascii=False) if as_json else sanitize_snippet(text)
    )


def cmd_scan(args: argparse.Namespace) -> int:
    kb = open_kb(args)
    if kb is None:
        return 1

    logger.info("Repository: %s", sanitize_snippet(str(kb.repo_root)))
    status = kb.refresh(
        force=args.force,
        evidence_limit=args.evidence_limit or None,
        refresh_header=args.refresh_header,
        use_gradle=args.gradle,
        gradle_timeout=args.gradle_timeout,
        gradle_offline=args.gradle_offline,
    )
    emit(_status_dict(status, kb), args.json, status.describe())
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    kb = open_kb(args)
    if kb is None:
        return 1

    status = kb.status(verify_content=args.verify_content)
    emit(_status_dict(status, kb), args.json, status.describe())
    return 0 if status.state is State.FRESH else 1


def cmd_layers(args: argparse.Namespace) -> int:
    kb = open_kb(args)
    if kb is None:
        return 1

    try:
        rows = kb.list_layers()
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1

    text = "\n".join(
        f"{row['id']:<20} {row['detected']}/{row['sections']} detected  {row['title']}"
        for row in rows
    )
    emit(rows, args.json, text)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    kb = open_kb(args)
    if kb is None:
        return 1

    try:
        layer = kb.get_layer(args.layer)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1

    if layer is None:
        logger.error("Unknown layer: %s", args.layer)
        return 1

    if args.section is None:
        safe_layer = Layer.from_dict(layer.to_dict())
        emit(safe_layer.to_dict(), args.json, _format_layer(safe_layer))
        return 0

    if layer.section(args.section) is None:
        available = ", ".join(item.id for item in layer.sections)
        logger.error(
            "Unknown section %s; available: %s",
            sanitize_snippet(args.section),
            sanitize_snippet(available),
        )
        return 1

    try:
        page = kb.get_section_page(
            args.layer,
            args.section,
            cursor=args.cursor,
            limit=args.limit or None,
        )
    except ValueError as exc:
        logger.error("%s", sanitize_snippet(str(exc)))
        return 1
    assert page is not None
    data = page.to_dict()
    text = _format_section(page.section)
    if page.total is not None:
        returned = len(page.section.items)
        text += f"\n\n  items {page.offset}-{(page.offset or 0) + returned} of {page.total}"
        if page.next_cursor is not None:
            text += f"; next cursor: {page.next_cursor}"
    emit(data, args.json, text)
    return 0


def cmd_overview(args: argparse.Namespace) -> int:
    kb = open_kb(args)
    if kb is None:
        return 1

    try:
        overview = kb.overview()
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1

    emit(overview, args.json, _format_overview(overview))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    kb = open_kb(args)
    if kb is None:
        return 1

    try:
        hits = kb.search(args.query, limit=args.limit, layer_id=args.layer)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1

    if not hits:
        emit([], args.json, f"Nothing matched {sanitize_snippet(args.query)!r}")
        return 1

    text = "\n".join(
        f"{hit.score:6.2f}  {hit.layer_id}/{hit.section.id}\n        {hit.section.summary}"
        for hit in hits
    )
    emit([hit.to_dict() for hit in hits], args.json, text)
    return 0


def _format_overview(overview: dict[str, Any]) -> str:
    overview = sanitize_public(overview)
    lines = [f"{overview['project']} ({overview['state']})", ""]
    highlights = overview.get("highlights", {})
    if isinstance(highlights, dict):
        width = max((len(key) for key in highlights), default=0)
        lines.extend(f"  {key:<{width}}  {value}" for key, value in highlights.items())
    layers = overview.get("layers", [])
    if isinstance(layers, list):
        lines.append("")
        lines.extend(
            f"  {layer['id']:<20} {layer['detected']}/{layer['sections']} detected"
            for layer in layers
        )
    return "\n".join(lines)


def _status_dict(status: Any, kb: KnowledgeBase) -> dict[str, Any]:
    return {
        "state": str(status.state),
        "repo_path": str(kb.repo_root),
        "kb_dir": str(kb.kb_dir),
        "files_count": status.files_count,
        "scanned_at": status.scanned_at,
        "tool_version": status.tool_version,
        "schema_version": status.schema_version,
        "git_commit": status.git_commit,
        "git_dirty": status.git_dirty,
        "git_root": status.git_root,
        "head_commit": status.head_commit,
        "changed_files": status.changed_files,
        "reason": status.reason,
        "scan_mode": status.scan_mode,
        "requested_scan_mode": status.requested_scan_mode,
        "gradle_fallback": status.gradle_fallback,
        "evidence_limit": status.evidence_limit,
        "refresh_action": status.refresh_action,
        "authority_change": status.authority_change,
        "summary": status.describe(),
    }


def _format_layer(layer: Layer) -> str:
    layer = Layer.from_dict(layer.to_dict())
    lines = [f"{layer.id}  {layer.title}", ""]
    for section in layer.sections:
        mark = "+" if section.detected else "-"
        origin = "  [gradle]" if section.source is Source.GRADLE else ""
        lines.append(f"[{mark}] {section.id:<32} {section.summary}{origin}")
    return "\n".join(lines)


def _format_section(section: Section) -> str:
    section = Section.from_dict(section.to_dict())
    label = "Detected" if section.detected else "Not found"
    if section.error:
        label = "Error"
    lines = [
        f"{section.title} ({section.id})",
        f"{label}: {section.error or section.summary}",
        f"source: {section.source}",
    ]
    if section.evidence:
        lines.append("")
        for item in section.evidence:
            if item.provenance.value == "gradle_model":
                location = f"Gradle project {item.project}, property {item.property}"
            elif item.provenance.value == "file":
                location = f"{item.path} ({item.entry_type})"
            else:
                location = (
                    f"{item.path}:{item.line_start}"
                    if item.line_start == item.line_end
                    else f"{item.path}:{item.line_start}-{item.line_end}"
                )
            lines.append(f"  {location}  {item.snippet}")
        if section.truncated:
            lines.append(f"  ... {section.evidence_total - len(section.evidence)} more")
    if section.items:
        lines.append("")
        lines.extend(f"  {item}" for item in section.items)
    if not section.is_signal:
        lines.append(f"inventory completeness: {section.inventory_completeness}")
        if section.collection_limit is not None:
            lines.append(f"collection limit: {section.collection_limit}")
        if section.collection_stop_reason:
            lines.append(f"collection stopped: {section.collection_stop_reason}")
    if section.limitations:
        lines.append("")
        lines.extend(f"  limitation: {item}" for item in section.limitations)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    prefix = 0
    while prefix < len(arguments) and arguments[prefix] in {"-v", "--verbose"}:
        prefix += 1
    if arguments[prefix : prefix + 1] == ["mcp"]:
        from coador.mcp_server import main as mcp_main

        return mcp_main(arguments[:prefix] + arguments[prefix + 1 :])

    parser = build_parser()
    args = parser.parse_args(arguments)
    configure_logging(args.verbose)
    if args.command is None:
        parser.print_help(sys.stderr)
        return 2
    try:
        return cast(int, args.func(args))
    except Exception as exc:
        logger.error("%s", sanitize_snippet(str(exc)) or "Operation failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
