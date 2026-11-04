"""Widgets for the core UI.

Split out of the former ``omni_trans_core/ui/widgets.py`` module; re-exports the
same public names so existing ``from omni_trans_core.ui.widgets import X``
imports keep working.
"""

from .data_table import DataTableWidget
from .generation_params import (
    GEMINI_BUDGET_STEP,
    GEMINI_FLASH_MAX_BUDGET,
    GEMINI_PRO_MAX_BUDGET,
    GEMINI_THINKING_LEVEL_KEYS,
    GEN_PARAMS_BUDGET_LABEL_MIN_WIDTH,
    GEN_PARAMS_COMMON_SPACING,
    GEN_PARAMS_MAIN_SPACING,
    GEN_PARAMS_NOTICE_COLOR,
    GEN_PARAMS_NOTICE_LEFT_MARGIN,
    GEN_PARAMS_NOTICE_STYLE,
    GEN_PARAMS_THINKING_WIDGET_LEFT_MARGIN,
    MAX_TOKENS_SPINBOX_RANGE,
    MAX_TOKENS_SPINBOX_STEP,
    PENALTY_SLIDER_RANGE,
    PENALTY_SPINBOX_RANGE,
    PRECISION_SPINBOX_STEP,
    SLIDER_TO_SPINBOX_FACTOR,
    TEMP_SLIDER_RANGE,
    TEMP_SPINBOX_RANGE,
    TOP_P_SLIDER_RANGE,
    TOP_P_SPINBOX_RANGE,
    GenerationParamsWidget,
)
from .languages import SourceLanguageWidget, TargetLanguageWidget
from .multi_connection import MultiConnectionTable
from .notifications import NotificationBell, NotificationCenter
from .rpm_status import RPMStatusWidget
from .translation_control import (
    EDIT_DEBOUNCE_INTERVAL_MS,
    EDITING_STATUS_FLASH_COLOR,
    EDITING_STATUS_FLASH_DURATION_MS,
    TranslationControlWidget,
)

__all__ = [
    "DataTableWidget",
    "EDIT_DEBOUNCE_INTERVAL_MS",
    "EDITING_STATUS_FLASH_COLOR",
    "EDITING_STATUS_FLASH_DURATION_MS",
    "GEMINI_BUDGET_STEP",
    "GEMINI_FLASH_MAX_BUDGET",
    "GEMINI_PRO_MAX_BUDGET",
    "GEMINI_THINKING_LEVEL_KEYS",
    "GEN_PARAMS_BUDGET_LABEL_MIN_WIDTH",
    "GEN_PARAMS_COMMON_SPACING",
    "GEN_PARAMS_MAIN_SPACING",
    "GEN_PARAMS_NOTICE_COLOR",
    "GEN_PARAMS_NOTICE_LEFT_MARGIN",
    "GEN_PARAMS_NOTICE_STYLE",
    "GEN_PARAMS_THINKING_WIDGET_LEFT_MARGIN",
    "GenerationParamsWidget",
    "MAX_TOKENS_SPINBOX_RANGE",
    "MAX_TOKENS_SPINBOX_STEP",
    "MultiConnectionTable",
    "NotificationBell",
    "NotificationCenter",
    "PENALTY_SLIDER_RANGE",
    "PENALTY_SPINBOX_RANGE",
    "PRECISION_SPINBOX_STEP",
    "RPMStatusWidget",
    "SLIDER_TO_SPINBOX_FACTOR",
    "SourceLanguageWidget",
    "TEMP_SLIDER_RANGE",
    "TEMP_SPINBOX_RANGE",
    "TOP_P_SLIDER_RANGE",
    "TOP_P_SPINBOX_RANGE",
    "TargetLanguageWidget",
    "TranslationControlWidget",
]
