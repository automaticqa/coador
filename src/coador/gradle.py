"""Heuristic helpers for Gradle build scripts (Groovy and Kotlin DSL)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class GradleBlock:
    name: str
    content: str
    start_line: int
    end_line: int


def parse_gradle_block(content: str, block_name: str) -> GradleBlock | None:
    """Return the first ``block_name { ... }`` block found by brace counting."""
    pattern = rf"(\b{re.escape(block_name)}\s*\{{)"
    match = re.search(pattern, content)
    if not match:
        return None

    start_pos = match.start()
    start_line = content[:start_pos].count("\n") + 1

    brace_count = 0
    in_block = False
    block_start = match.end() - 1
    block_end = block_start

    for i, ch in enumerate(content[block_start:], start=block_start):
        if ch == "{":
            brace_count += 1
            in_block = True
        elif ch == "}":
            brace_count -= 1
            if in_block and brace_count == 0:
                block_end = i + 1
                break

    block_content = content[block_start:block_end]
    end_line = start_line + block_content.count("\n")

    return GradleBlock(
        name=block_name,
        content=block_content,
        start_line=start_line,
        end_line=end_line,
    )


def extract_string_values(text: str) -> list[str]:
    pattern = r'["\']([^"\']+)["\']'
    return re.findall(pattern, text)


def parse_include_modules(settings_content: str) -> list[str]:
    """Collect ``:module`` paths from ``include(...)`` calls in a settings script."""
    modules: set[str] = set()

    include_blocks = re.findall(r"include\s*\(([^)]*)\)", settings_content, flags=re.DOTALL)
    for block in include_blocks:
        values = extract_string_values(block)
        for val in values:
            if val.startswith(":"):
                modules.add(val)

    lines = settings_content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith("//") or line.startswith("#"):
            i += 1
            continue

        if "include" in line:
            block_lines = [line]
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if not next_line:
                    break
                if next_line.startswith(("'", '"', ":")):
                    block_lines.append(lines[j])
                    if not next_line.endswith(","):
                        j += 1
                        break
                    j += 1
                    continue
                break
            values = extract_string_values("\n".join(block_lines))
            for val in values:
                if val.startswith(":"):
                    modules.add(val)
            i = j
            continue

        i += 1

    return sorted(modules)


def parse_project_dependencies(build_content: str) -> list[str]:
    """Collect ``project(":x")`` and type-safe ``projects.x.y`` accessors."""
    deps: set[str] = set()

    pattern = r'project\s*\(\s*["\'](:[\w:]+)["\']\s*\)'
    deps.update(re.findall(pattern, build_content))

    accessor_pattern = r"projects(?:\.[A-Za-z0-9_]+)+"
    excluded = {"getByName", "findByName", "named", "register", "create", "maybeCreate"}
    for match in re.findall(accessor_pattern, build_content):
        parts = match.split(".")[1:]
        if not parts or any(p in excluded for p in parts):
            continue
        deps.add(":" + ":".join(parts))

    return sorted(deps)


def parse_plugins(build_content: str) -> list[str]:
    """Collect plugin ids from ``plugins {}`` blocks and legacy ``apply plugin:`` lines."""
    plugins: set[str] = set()

    plugins_block = parse_gradle_block(build_content, "plugins")
    if plugins_block:
        id_pattern = r'id\s*\(\s*["\']([^"\']+)["\']\s*\)'
        plugins.update(re.findall(id_pattern, plugins_block.content))

        alias_pattern = r"alias\s*\(\s*[\w.]+\.([^)]+)\s*\)"
        plugins.update(re.findall(alias_pattern, plugins_block.content))

    apply_pattern = r'apply\s+plugin\s*:\s*["\']([^"\']+)["\']'
    plugins.update(re.findall(apply_pattern, build_content))

    return sorted(plugins)


# Calls that create a named entry inside a Gradle container.
_CONTAINER_CALL_RE = re.compile(
    r"\b(?:create|register|maybeCreate|named|getByName)\s*\(\s*[\"']([A-Za-z0-9_]+)[\"']"
)
# ``name {`` at the top level of a container block declares an entry as well.
_TRAILING_NAME_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*$")
# Language and DSL constructs that also read as ``word {`` but name nothing.
_NOT_CONTAINER_NAMES = frozenset(
    {
        "if",
        "else",
        "when",
        "for",
        "while",
        "do",
        "try",
        "catch",
        "finally",
        "fun",
        "val",
        "var",
        "return",
        "it",
        "this",
        "apply",
        "also",
        "let",
        "run",
        "with",
        "forEach",
        "map",
        "filter",
        "each",
        "all",
        "configureEach",
        "matching",
        "withType",
    }
)


def extract_container_names(block_content: str) -> list[str]:
    """Return the entries declared directly inside a Gradle container block.

    Only the first nesting level is considered, so options configured inside an
    entry (``buildConfigField``, ``firebaseAppDistribution`` and friends) are not
    mistaken for entries of their own.
    """
    names: list[str] = []
    depth = 0
    segment: list[str] = []

    for char in block_content:
        if char == "{":
            if depth == 1:
                _collect_name("".join(segment), names)
            depth += 1
            segment = []
        elif char == "}":
            if depth == 1:
                _collect_calls("".join(segment), names)
            depth = max(0, depth - 1)
            segment = []
        elif depth == 1:
            segment.append(char)

    _collect_calls("".join(segment), names)
    return list(dict.fromkeys(names))


def _collect_name(segment: str, names: list[str]) -> None:
    calls = _CONTAINER_CALL_RE.findall(segment)
    if calls and segment.rstrip().endswith(")"):
        names.append(calls[-1])
        return

    match = _TRAILING_NAME_RE.search(segment)
    if match and match.group(1) not in _NOT_CONTAINER_NAMES:
        names.append(match.group(1))


def _collect_calls(segment: str, names: list[str]) -> None:
    names.extend(match.group(1) for match in _CONTAINER_CALL_RE.finditer(segment))


def extract_flavor_names(build_content: str) -> list[str]:
    """Return the product flavours declared in ``productFlavors {}``."""
    block = parse_gradle_block(build_content, "productFlavors")
    return extract_container_names(block.content) if block else []


def extract_build_types(build_content: str) -> list[str]:
    """Return the build types declared in ``buildTypes {}``."""
    block = parse_gradle_block(build_content, "buildTypes")
    return extract_container_names(block.content) if block else []
