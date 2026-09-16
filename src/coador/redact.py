"""Redaction of secrets in evidence snippets before they reach the knowledge base."""

from __future__ import annotations

import re
from typing import Any

REDACTED = "***REDACTED***"

SECRET_VALUE_RE = re.compile(
    r"(?i)([\w.-]*(?:api[_-]?key|apikey|secret|token|password|passwd|credential|client[_-]?secret|"
    r"private[_-]?key|authorization)[\w.-]*)"
    # A declared type may sit between the name and the value: ``val TOKEN: String = "..."``.
    r"(\s*(?::\s*[A-Za-z_][\w<>?.]*\s*=|[:=])\s*)"
    r"([\"'])([^\"']+)([\"'])"
)
BUILD_CONFIG_RE = re.compile(
    r"(?P<prefix>buildConfigField\s*\(\s*[^,]+,\s*[\"'](?P<name>[^\"']+)[\"']\s*,\s*)"
    r"(?P<value>\"([^\"\\]|\\.)*\"|'([^'\\]|\\.)*')"
    r"(?P<suffix>\s*\))",
    re.IGNORECASE,
)
SECRET_NAME_RE = re.compile(
    r"(?i)(api[_-]?key|apikey|secret|token|password|passwd|credential|client[_-]?secret|"
    r"private[_-]?key|auth)"
)
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
BASE64_RE = re.compile(r"([\"'])(?=[A-Za-z0-9+/=]{24,})(?=.*[0-9+/=])[A-Za-z0-9+/=]+([\"'])")
BEARER_RE = re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9\-._~+/]+=*")
# Bare identifiers that are configuration values in their own right: project ids,
# consent ids, API client ids. They carry no secret-sounding name to match on.
UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
# Long hexadecimal strings quoted as values: signing hashes, keys, tokens.
LONG_HEX_RE = re.compile(r"([\"'])[0-9a-f]{32,}\1", re.IGNORECASE)


# Preserve line geometry: provenance uses the original source's line numbers.
def _mask(value: str) -> str:
    return REDACTED + "\n" * value.count("\n")


_NAME = (
    r"[\w.-]*(?:api[_-]?key|secret|token|password|passwd|credential|"
    r"private[_-]?key|authorization)[\w.-]*"
)
_QUOTED = (
    r'''(?:"""[\s\S]*?"""|\x27\x27\x27[\s\S]*?\x27\x27\x27|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')'''
)
_QUOTED_RE = re.compile(_QUOTED)
_ASSIGNMENT = re.compile(
    rf"(?i)(\b{_NAME}[\"']?\s*(?::\s*[A-Za-z_][\w<>?.]*\s*=|[:=])\s*)"
    rf"""({_QUOTED}|[^\s,;<>"'+]+)"""
)
_YAML_BLOCK = re.compile(rf"(?im)^(\s*{_NAME}\s*:\s*[|>][-+]?[^\n]*\n)((?:[ \t]+[^\n]*(?:\n|$))+)")
_XML_SECRET = re.compile(
    rf"""(?is)(<(?:string|item)\b[^>]*\bname\s*=\s*["']{_NAME}["'][^>]*>)(.*?)(</(?:string|item)\s*>)"""
)
_PEM = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]*PRIVATE KEY)-----[\s\S]*?-----END (?:[A-Z0-9 ]*PRIVATE KEY)-----"
)
_URL_AUTH = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^/\s<>\"']*@")
_URL_QUERY = re.compile(rf"(?i)([?&](?:{_NAME})=)[^&#\s<>\"']*")
_HEADER = re.compile(
    r"(?im)(\b(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key)\s*:\s*)[^\r\n]+"
)


def _assignment(prefix: str, value: str) -> str:
    if (
        value.startswith(REDACTED)
        or value in ("|", ">", "true", "false", "null")
        or (
            value.isdecimal()
            and re.search(r"(?:count|size|length|timeout)\W*[:=]", prefix, re.IGNORECASE)
        )
    ):
        return prefix + value
    if re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\(\)", value):
        return prefix + value
    if value.startswith(('"""', "'''")):
        return prefix + value[:3] + _mask(value) + value[:3]
    if value.startswith(('"', "'")):
        return prefix + value[0] + _mask(value) + value[0]
    return prefix + _mask(value)


def _expression_end(text: str, start: int, atom_end: int) -> int:
    """Suppress a sensitive RHS up to a quote-aware, balanced statement boundary.

    This does not interpret code. Unsupported expression contents are suppressed
    along with the literals instead of being returned as unfiltered suffixes.
    """
    position = start
    stack: list[str] = []
    previous = ""
    while position < len(text):
        char = text[position]
        if char in "\"'":
            # An assignment embedded in a quoted URL/string ends at that
            # containing string's quote, not at the next quoted source value.
            if position == atom_end and text[start] not in "\"'":
                break
            quoted = _QUOTED_RE.match(text, position)
            if quoted is None:
                return len(text)
            position = quoted.end()
            previous = "literal"
            continue
        if char in "([{":
            stack.append({"(": ")", "[": "]", "{": "}"}[char])
        elif char in ")]}":
            if not stack or stack[-1] != char:
                break
            stack.pop()
        elif (char in ";,#" and not stack) or (
            char in "\r\n"
            and not stack
            and previous not in "+-*/%?:&|^=<>"
            and not text[position:].lstrip().startswith(tuple("+-*/%?:&|^=<>"))
        ):
            break
        if not char.isspace():
            previous = char
        position += 1
    return position


def _redact_assignments(text: str) -> str:
    parts: list[str] = []
    cursor = 0
    for match in _ASSIGNMENT.finditer(text):
        if match.start() < cursor:
            continue
        prefix, value = match.groups()
        end = match.end()
        end = _expression_end(text, match.start(2), end)
        value = text[match.start(2) : end].rstrip(" \t")
        end = match.start(2) + len(value)
        parts.extend((text[cursor : match.start()], _assignment(prefix, value)))
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


def sanitize_snippet(snippet: str) -> str:
    """Replace secret-looking values in ``snippet`` with a redaction marker."""
    if not snippet:
        return snippet

    sanitized = _PEM.sub(lambda m: _mask(m.group(0)), snippet)
    sanitized = _XML_SECRET.sub(lambda m: m.group(1) + _mask(m.group(2)) + m.group(3), sanitized)
    sanitized = _YAML_BLOCK.sub(lambda m: m.group(1) + "  " + _mask(m.group(2)), sanitized)
    sanitized = _redact_assignments(sanitized)
    sanitized = _URL_AUTH.sub(lambda m: m.group(1) + REDACTED + "@", sanitized)
    sanitized = _URL_QUERY.sub(lambda m: m.group(1) + REDACTED, sanitized)
    sanitized = _HEADER.sub(lambda m: m.group(1) + REDACTED, sanitized)
    sanitized = BUILD_CONFIG_RE.sub(
        lambda m: (
            f"{m.group('prefix')}{m.group('value')[0]}{REDACTED}"
            f"{m.group('value')[0]}{m.group('suffix')}"
            if SECRET_NAME_RE.search(m.group("name"))
            else m.group(0)
        ),
        sanitized,
    )
    sanitized = JWT_RE.sub(REDACTED, sanitized)
    sanitized = BASE64_RE.sub(rf"\1{REDACTED}\2", sanitized)
    sanitized = BEARER_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", sanitized)
    sanitized = UUID_RE.sub(REDACTED, sanitized)
    sanitized = LONG_HEX_RE.sub(rf"\1{REDACTED}\1", sanitized)
    return sanitized


def sanitize_public(value: Any) -> Any:
    """Clean operational/adaptor data; source citations require model validation too."""
    if isinstance(value, str):
        return sanitize_snippet(value)
    if isinstance(value, dict):
        return {sanitize_snippet(str(key)): sanitize_public(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_public(item) for item in value]
    return value
