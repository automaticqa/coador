"""Ask Gradle itself what the project looks like.

The heuristic detectors read build files as text, which is fast and needs no
toolchain, but it cannot see through convention plugins, ``build-logic`` or
flavours generated in a loop. This module runs the real build's configuration
phase through an init script and reads the resulting model, so those projects
are described from ground truth instead of guessed at.

The probe is optional by design: it needs a JDK and a Gradle wrapper, it takes
as long as a Gradle configuration takes, and any failure simply leaves the
heuristic answers in place.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NoReturn

from coador.paths import UnsafePathError, checked_path
from coador.redact import sanitize_snippet

logger = logging.getLogger(__name__)

INIT_SCRIPT = Path(__file__).parent / "data" / "coador_probe.gradle"
MODEL_BEGIN = "COADOR_MODEL_BEGIN"
MODEL_END = "COADOR_MODEL_END"
DEFAULT_TIMEOUT_SECONDS = 600


class GradleProbeError(RuntimeError):
    """Raised when the Gradle model could not be produced."""


@dataclass(frozen=True)
class ProductFlavor:
    name: str
    dimension: str | None = None
    application_id_suffix: str | None = None


@dataclass(frozen=True)
class AndroidModel:
    """The Android DSL of one Gradle project, as configured."""

    namespace: str | None = None
    application_id: str | None = None
    min_sdk: int | None = None
    target_sdk: int | None = None
    compile_sdk: int | None = None
    test_instrumentation_runner: str | None = None
    build_types: tuple[str, ...] = ()
    flavor_dimensions: tuple[str, ...] = ()
    product_flavors: tuple[ProductFlavor, ...] = ()
    animations_disabled: bool | None = None
    test_execution: str | None = None
    source_sets: tuple[str, ...] = ()
    unavailable_properties: tuple[str, ...] = ()
    availability_reported: bool = False

    @property
    def is_application(self) -> bool:
        return self.application_id is not None


@dataclass(frozen=True)
class GradleProject:
    """One project (module) of the build."""

    path: str
    directory: str
    plugins: tuple[str, ...] = ()
    android: AndroidModel | None = None
    android_kind: str | None = None
    project_dependencies: tuple[str, ...] = ()
    dependency_collection_complete: bool | None = None

    @property
    def kind(self) -> str:
        if self.android is None:
            return "jvm" if any("kotlin" in plugin for plugin in self.plugins) else "other"
        if self.android_kind in {"application", "library"}:
            return self.android_kind
        return "application" if self.android.is_application else "library"


@dataclass(frozen=True)
class GradleModel:
    """The configured model of a whole build."""

    root_project: str
    gradle_version: str
    projects: tuple[GradleProject, ...] = field(default_factory=tuple)
    root_dir: str = ""

    @property
    def android_projects(self) -> tuple[GradleProject, ...]:
        return tuple(project for project in self.projects if project.android is not None)

    def project(self, path: str) -> GradleProject | None:
        for project in self.projects:
            if project.path == path:
                return project
        return None


def probe(
    repo_root: Path,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    offline: bool = False,
) -> GradleModel:
    """Run the Gradle configuration phase and return the resulting model."""
    repo_root = repo_root.resolve()
    wrapper = repo_root / ("gradlew.bat" if _is_windows() else "gradlew")
    try:
        wrapper = checked_path(repo_root, wrapper)
    except UnsafePathError:
        raise GradleProbeError(
            f"Gradle wrapper is unsafe in {sanitize_snippet(str(repo_root))}"
        ) from None
    if not wrapper.exists():
        raise GradleProbeError(f"No Gradle wrapper in {sanitize_snippet(str(repo_root))}")
    if not INIT_SCRIPT.exists():  # pragma: no cover - packaging accident
        raise GradleProbeError("Gradle probe init script is unavailable")

    command = [
        str(wrapper),
        "--init-script",
        str(INIT_SCRIPT),
        "--quiet",
        "--no-daemon",
        "help",
    ]
    if offline:
        command.insert(-1, "--offline")

    logger.info(
        "Running Gradle configuration in %s (timeout %ds)",
        sanitize_snippet(str(repo_root)),
        timeout,
    )
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise GradleProbeError(f"Gradle probe timed out after {timeout}s") from None
    except OSError:
        raise GradleProbeError("Gradle probe could not start") from None

    if MODEL_BEGIN not in completed.stdout:
        raise GradleProbeError(_failure_reason(completed))

    return parse_model(completed.stdout, repo_root=repo_root)


def parse_model(output: str, *, repo_root: Path | None = None) -> GradleModel:
    """Extract the JSON model from Gradle's output.

    An init script is applied to every build in the tree, so a project with a
    ``buildSrc`` or an included build prints one block per build. The block
    describing the most projects is the main build.
    """
    blocks: list[dict[str, Any]] = []
    position = 0
    while True:
        start = output.find(MODEL_BEGIN, position)
        if start < 0:
            break
        end = output.find(MODEL_END, start)
        if end < 0:
            break
        payload = output[start + len(MODEL_BEGIN) : end].strip()
        position = end + len(MODEL_END)
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            raise GradleProbeError("Gradle model JSON is invalid") from None
        if isinstance(parsed, dict):
            blocks.append(parsed)

    if not blocks:
        raise GradleProbeError("Gradle produced no model")

    for block in blocks:
        if not isinstance(block.get("projects", []), list):
            _invalid_model()

    if repo_root is not None:
        requested = repo_root.resolve()
        selected = [
            block
            for block in blocks
            if isinstance(block.get("rootDir"), str)
            and Path(str(block["rootDir"])).resolve() == requested
        ]
        if len(selected) != 1:
            raise GradleProbeError("Gradle produced no unique model for the requested root")
        data = selected[0]
    elif len(blocks) == 1:
        data = blocks[0]
    else:
        raise GradleProbeError("Gradle produced multiple models without a requested root")
    try:
        return GradleModel(
            root_project=str(data.get("rootProject", "")),
            gradle_version=str(data.get("gradleVersion", "")),
            projects=tuple(_project(entry) for entry in data.get("projects", [])),
            root_dir=str(data.get("rootDir", "")),
        )
    except (AttributeError, TypeError, ValueError):
        _invalid_model()


def _project(entry: object) -> GradleProject:
    if not isinstance(entry, dict):
        _invalid_model()
    android = entry.get("android")
    if android is not None and not isinstance(android, dict):
        _invalid_model()
    plugins = entry.get("plugins", [])
    dependencies = entry.get("projectDependencies", [])
    dependency_complete = entry.get("projectDependenciesComplete")
    android_kind = entry.get("androidPluginKind")
    if (
        not isinstance(plugins, list)
        or not isinstance(dependencies, list)
        or (dependency_complete is not None and not isinstance(dependency_complete, bool))
        or android_kind not in (None, "application", "library")
    ):
        _invalid_model()
    return GradleProject(
        path=str(entry.get("path", "")),
        directory=str(entry.get("dir", "")),
        plugins=tuple(str(plugin) for plugin in plugins),
        android=_android(android) if android is not None else None,
        android_kind=android_kind,
        project_dependencies=tuple(str(path) for path in dependencies),
        dependency_collection_complete=dependency_complete,
    )


def _android(entry: dict[str, Any]) -> AndroidModel:
    test_options = entry.get("testOptions")
    if test_options is None:
        test_options = {}
    build_types = entry.get("buildTypes", [])
    flavor_dimensions = entry.get("flavorDimensions", [])
    product_flavors = entry.get("productFlavors", [])
    source_sets = entry.get("sourceSets", [])
    unavailable = entry.get("unavailableProperties", [])
    if (
        not isinstance(test_options, dict)
        or not isinstance(build_types, list)
        or not isinstance(flavor_dimensions, list)
        or not isinstance(product_flavors, list)
        or not isinstance(source_sets, list)
        or not isinstance(unavailable, list)
        or any(not isinstance(flavor, dict) for flavor in product_flavors)
    ):
        _invalid_model()
    return AndroidModel(
        namespace=_as_str(entry.get("namespace")),
        application_id=_as_str(entry.get("applicationId")),
        min_sdk=_as_int(entry.get("minSdk")),
        target_sdk=_as_int(entry.get("targetSdk")),
        compile_sdk=_as_int(entry.get("compileSdk")),
        test_instrumentation_runner=_as_str(entry.get("testInstrumentationRunner")),
        build_types=tuple(str(name) for name in build_types),
        flavor_dimensions=tuple(str(name) for name in flavor_dimensions),
        product_flavors=tuple(
            ProductFlavor(
                name=str(flavor.get("name", "")),
                dimension=_as_str(flavor.get("dimension")),
                application_id_suffix=_as_str(flavor.get("applicationIdSuffix")),
            )
            for flavor in product_flavors
        ),
        animations_disabled=_as_bool(test_options.get("animationsDisabled")),
        test_execution=_as_str(test_options.get("execution")),
        source_sets=tuple(str(name) for name in source_sets),
        unavailable_properties=tuple(str(name) for name in unavailable),
        availability_reported="unavailableProperties" in entry,
    )


def _failure_reason(completed: subprocess.CompletedProcess[str]) -> str:
    return f"Gradle probe produced no model (exit {completed.returncode})"


def _invalid_model() -> NoReturn:
    raise GradleProbeError("Gradle model has invalid structure") from None


def _is_windows() -> bool:
    import os

    return os.name == "nt"


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _as_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None
