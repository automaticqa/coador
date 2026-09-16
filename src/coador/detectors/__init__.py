"""Signal detectors grouped by knowledge-base layer."""

from coador.detectors.architecture import get_architecture_detectors
from coador.detectors.base import BaseDetector, DetectionResult, Evidence
from coador.detectors.build import get_build_detectors
from coador.detectors.ci_cd import get_ci_cd_detectors
from coador.detectors.config import get_config_detectors
from coador.detectors.dependencies import get_dependencies_detectors
from coador.detectors.modules import get_modules_detectors
from coador.detectors.overview import get_overview_detectors
from coador.detectors.testing import get_testing_detectors
from coador.detectors.ui_testing import get_ui_testing_detectors

__all__ = [
    "BaseDetector",
    "DetectionResult",
    "Evidence",
    "get_architecture_detectors",
    "get_build_detectors",
    "get_ci_cd_detectors",
    "get_config_detectors",
    "get_dependencies_detectors",
    "get_modules_detectors",
    "get_overview_detectors",
    "get_testing_detectors",
    "get_ui_testing_detectors",
]
