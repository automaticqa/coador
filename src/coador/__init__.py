"""coador: a deterministic, evidence-backed knowledge base of an Android project.

The package scans a Gradle-based Android repository, records detected signals
(build system, architecture, modules, configuration, dependencies, testing,
UI testing, CI/CD) with source-line, file-level or Gradle-model provenance, and exposes the result
to AI coding agents through a CLI and an MCP server.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
