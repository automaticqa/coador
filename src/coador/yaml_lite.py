"""Minimal, dependency-free heuristics for CI YAML files."""

from __future__ import annotations

import re

_RESERVED_TOP_LEVEL_KEYS = ("stages", "variables", "include", "default", "workflow")


def parse_yaml_jobs(yaml_content: str) -> list[str]:
    """Return top-level keys that look like GitLab CI jobs (column 0, not reserved, not hidden)."""
    jobs: list[str] = []

    for line in yaml_content.splitlines():
        if line and not line.startswith(" ") and not line.startswith("#") and ":" in line:
            job_name = line.split(":")[0].strip()
            if (
                job_name
                and not job_name.startswith(".")
                and job_name not in _RESERVED_TOP_LEVEL_KEYS
            ):
                jobs.append(job_name)

    return jobs


def parse_yaml_stages(yaml_content: str) -> list[str]:
    """Return the items of a top-level ``stages:`` list."""
    stages: list[str] = []

    match = re.search(r"stages:\s*\n((?:\s+-\s+\w+\n?)+)", yaml_content)
    if match:
        stages_block = match.group(1)
        stages = re.findall(r"-\s+(\w+)", stages_block)

    return stages
