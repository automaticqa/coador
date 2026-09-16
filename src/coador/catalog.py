"""Gradle version catalog (``libs.versions.toml``) parsing.

The catalog is real TOML, so it is parsed with ``tomllib`` rather than guessed
at with regular expressions: that is what makes it possible to report actual
library versions instead of echoing raw lines.
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from coador.textscan import read_file_content

logger = logging.getLogger(__name__)

CATALOG_PATH = "gradle/libs.versions.toml"


@dataclass(frozen=True)
class LibraryEntry:
    """One entry of the ``[libraries]`` table, with its version resolved."""

    alias: str
    module: str
    version: str | None = None
    version_ref: str | None = None

    @property
    def coordinates(self) -> str:
        return f"{self.module}:{self.version}" if self.version else self.module


@dataclass(frozen=True)
class VersionCatalog:
    """The parsed contents of a Gradle version catalog."""

    path: Path
    versions: dict[str, str] = field(default_factory=dict)
    libraries: dict[str, LibraryEntry] = field(default_factory=dict)
    plugins: dict[str, str] = field(default_factory=dict)
    bundles: dict[str, list[str]] = field(default_factory=dict)

    def find(self, *keywords: str) -> list[LibraryEntry]:
        """Return the libraries whose alias or module mentions any keyword."""
        lowered = [keyword.lower() for keyword in keywords]
        return [
            entry
            for entry in self.libraries.values()
            if any(word in entry.alias.lower() or word in entry.module.lower() for word in lowered)
        ]


def load_catalog(repo_root: Path) -> VersionCatalog | None:
    """Read and parse ``gradle/libs.versions.toml`` if the project has one."""
    repo_root = repo_root.resolve()
    path = repo_root / CATALOG_PATH
    if not path.exists():
        return None

    try:
        content = read_file_content(path, root=repo_root)
        if content is None:
            return None
        data = tomllib.loads(content)
    except (OSError, tomllib.TOMLDecodeError):
        logger.warning("Could not parse version catalog")
        return VersionCatalog(path=path)

    versions = {key: str(value) for key, value in _table(data, "versions").items()}
    return VersionCatalog(
        path=path,
        versions=versions,
        libraries=_parse_libraries(_table(data, "libraries"), versions),
        plugins=_parse_plugins(_table(data, "plugins")),
        bundles={
            alias: [str(item) for item in entries]
            for alias, entries in _table(data, "bundles").items()
            if isinstance(entries, list)
        },
    )


def _table(data: dict[str, object], name: str) -> dict[str, object]:
    value = data.get(name)
    return value if isinstance(value, dict) else {}


def _parse_libraries(table: dict[str, object], versions: dict[str, str]) -> dict[str, LibraryEntry]:
    libraries: dict[str, LibraryEntry] = {}

    for alias, value in table.items():
        if isinstance(value, str):
            # Shorthand form: "group:name:version".
            group_and_name, _, inline_version = value.rpartition(":")
            libraries[alias] = LibraryEntry(
                alias=alias,
                module=group_and_name or value,
                version=inline_version or None,
            )
            continue
        if not isinstance(value, dict):
            continue

        module = _module_of(value)
        if module is None:
            continue

        version_ref, resolved = _version_of(value, versions)
        libraries[alias] = LibraryEntry(
            alias=alias, module=module, version=resolved, version_ref=version_ref
        )

    return libraries


def _module_of(entry: dict[str, object]) -> str | None:
    module = entry.get("module")
    if isinstance(module, str):
        return module

    group, name = entry.get("group"), entry.get("name")
    if isinstance(group, str) and isinstance(name, str):
        return f"{group}:{name}"
    return None


def _version_of(
    entry: dict[str, object], versions: dict[str, str]
) -> tuple[str | None, str | None]:
    version = entry.get("version")
    if isinstance(version, str):
        return None, version
    if isinstance(version, dict):
        ref = version.get("ref")
        if isinstance(ref, str):
            return ref, versions.get(ref)
        require = version.get("require") or version.get("prefer")
        if isinstance(require, str):
            return None, require
    return None, None


def _parse_plugins(table: dict[str, object]) -> dict[str, str]:
    plugins: dict[str, str] = {}
    for alias, value in table.items():
        if isinstance(value, str):
            plugins[alias] = value.partition(":")[0]
        elif isinstance(value, dict):
            plugin_id = value.get("id")
            if isinstance(plugin_id, str):
                plugins[alias] = plugin_id
    return plugins
