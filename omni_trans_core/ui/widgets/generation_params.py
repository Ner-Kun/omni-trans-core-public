import logging

from PySide6 import QtCore, QtWidgets
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    DoubleSpinBox,
    Slider,
    SpinBox,
    StrongBodyLabel,
)

from ... import settings
from ...localization_manager import auto_register, loc_man, translate
from ..animations import UIAnimator
from ..base_widgets import fix_spin_box_editor

logger = logging.getLogger("CORE_UI.widgets")

GEN_PARAMS_MAIN_SPACING = 10
GEN_PARAMS_NOTICE_COLOR = "#f1fa8c"
GEN_PARAMS_NOTICE_STYLE = "font-style: italic;"
GEN_PARAMS_NOTICE_LEFT_MARGIN = 15
GEN_PARAMS_THINKING_WIDGET_LEFT_MARGIN = 15
GEN_PARAMS_BUDGET_LABEL_MIN_WIDTH = 50
GEN_PARAMS_SPINBOX_MIN_WIDTH = 80
GEN_PARAMS_SPINBOX_MAX_WIDTH = 110
GEN_PARAMS_COMBO_MIN_WIDTH = 120
GEN_PARAMS_COMBO_MAX_WIDTH = 220
GEN_PARAMS_COMMON_SPACING = 10
SLIDER_TO_SPINBOX_FACTOR = 100.0
TEMP_SLIDER_RANGE = (0, 200)
TEMP_SPINBOX_RANGE = (0.0, 2.0)
PRECISION_SPINBOX_STEP = 0.01
TOP_P_SLIDER_RANGE = (0, 100)
TOP_P_SPINBOX_RANGE = (0.0, 1.0)
MAX_TOKENS_SPINBOX_RANGE = (0, 1_000_000)
MAX_TOKENS_SPINBOX_STEP = 64
PENALTY_SLIDER_RANGE = (-200, 200)
PENALTY_SPINBOX_RANGE = (-2.0, 2.0)
GEMINI_PRO_MAX_BUDGET = 32768
GEMINI_FLASH_MAX_BUDGET = 24576
GEMINI_BUDGET_STEP = 512
GEMINI_THINKING_LEVEL_KEYS = (
    "widget.generation_params.thinking_level.low",
    "widget.generation_params.thinking_level.high",
)


@auto_register(
    ("title_label", "text", "widget.generation_params.title"),
    ("use_context_check", "text", "widget.generation_params.use_content_context"),
    ("use_context_check", "toolTip", "widget.generation_params.use_content_context.tooltip"),
    ("enable_thinking_check", "text", "widget.generation_params.enable_model_thinking"),
    ("enable_thinking_check", "toolTip", "widget.generation_params.enable_model_thinking.tooltip"),
    ("budget_label", "text", "widget.generation_params.thinking_budget.label"),
    ("temperature_label", "text", "widget.generation_params.temperature.label"),
    ("top_p_label", "text", "widget.generation_params.top_p.label"),
    ("max_tokens_label", "text", "widget.generation_params.max_output_tokens.label"),
    ("max_tokens_spin", "toolTip", "widget.generation_params.max_output_tokens.tooltip"),
    ("frequency_penalty_label", "text", "widget.generation_params.frequency_penalty.label"),
    ("presence_penalty_label", "text", "widget.generation_params.presence_penalty.label"),
)
class GenerationParamsWidget(CardWidget):
    params_changed = QtCore.Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._updating = False
        self._is_gemini_3 = False
        self._build_ui()
        self._refresh_dynamic_localization()
        self.connect_signals()
        loc_man.language_changed.connect(self._refresh_dynamic_localization)
        logger.debug("GenerationParamsWidget initialized")

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        self.title_label = StrongBodyLabel(self)
        layout.addWidget(self.title_label)

        self.use_context_check = CheckBox(self)
        layout.addWidget(self.use_context_check)

        self.enable_thinking_check = CheckBox(self)
        layout.addWidget(self.enable_thinking_check)

        form = QtWidgets.QFormLayout()
        form.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)

        self.budget_row = QtWidgets.QWidget(self)
        budget_layout = QtWidgets.QHBoxLayout(self.budget_row)
        budget_layout.setContentsMargins(0, 0, 0, 0)
        self.budget_label = BodyLabel(self.budget_row)
        self.budget_spin = SpinBox(self.budget_row)
        self.budget_spin.setRange(-1, GEMINI_PRO_MAX_BUDGET)
        self.budget_spin.setSingleStep(GEMINI_BUDGET_STEP)
        budget_layout.addWidget(self.budget_spin, 1)
        form.addRow(self.budget_label, self.budget_row)

        self.level_row = QtWidgets.QWidget(self)
        level_layout = QtWidgets.QHBoxLayout(self.level_row)
        level_layout.setContentsMargins(0, 0, 0, 0)
        self.level_label = BodyLabel(self.level_row)
        self.level_combo = ComboBox(self.level_row)
        level_layout.addWidget(self.level_combo, 1)
        form.addRow(self.level_label, self.level_row)

        self.temperature_label = BodyLabel(self)
        self.temp_slider = Slider(QtCore.Qt.Orientation.Horizontal, self)
        self.temp_slider.setRange(*TEMP_SLIDER_RANGE)
        self.temp_spin = DoubleSpinBox(self)
        self.temp_spin.setRange(*TEMP_SPINBOX_RANGE)
        self.temp_spin.setSingleStep(PRECISION_SPINBOX_STEP)
        temp_row = QtWidgets.QWidget(self)
        temp_layout = QtWidgets.QHBoxLayout(temp_row)
        temp_layout.setContentsMargins(0, 0, 0, 0)
        temp_layout.addWidget(self.temp_slider, 1)
        temp_layout.addWidget(self.temp_spin)
        form.addRow(self.temperature_label, temp_row)

        self.top_p_label = BodyLabel(self)
        self.top_p_slider = Slider(QtCore.Qt.Orientation.Horizontal, self)
        self.top_p_slider.setRange(*TOP_P_SLIDER_RANGE)
        self.top_p_spin = DoubleSpinBox(self)
        self.top_p_spin.setRange(*TOP_P_SPINBOX_RANGE)
        self.top_p_spin.setSingleStep(PRECISION_SPINBOX_STEP)
        top_p_row = QtWidgets.QWidget(self)
        top_p_layout = QtWidgets.QHBoxLayout(top_p_row)
        top_p_layout.setContentsMargins(0, 0, 0, 0)
        top_p_layout.addWidget(self.top_p_slider, 1)
        top_p_layout.addWidget(self.top_p_spin)
        form.addRow(self.top_p_label, top_p_row)

        self.max_tokens_label = BodyLabel(self)
        self.max_tokens_spin = SpinBox(self)
        self.max_tokens_spin.setRange(*MAX_TOKENS_SPINBOX_RANGE)
        self.max_tokens_spin.setSingleStep(MAX_TOKENS_SPINBOX_STEP)
        form.addRow(self.max_tokens_label, self.max_tokens_spin)

        self.frequency_penalty_label = BodyLabel(self)
        self.freq_penalty_slider = Slider(QtCore.Qt.Orientation.Horizontal, self)
        self.freq_penalty_slider.setRange(*PENALTY_SLIDER_RANGE)
        self.freq_penalty_spin = DoubleSpinBox(self)
        self.freq_penalty_spin.setRange(*PENALTY_SPINBOX_RANGE)
        self.freq_penalty_spin.setSingleStep(PRECISION_SPINBOX_STEP)
        freq_row = QtWidgets.QWidget(self)
        freq_layout = QtWidgets.QHBoxLayout(freq_row)
        freq_layout.setContentsMargins(0, 0, 0, 0)
        freq_layout.addWidget(self.freq_penalty_slider, 1)
        freq_layout.addWidget(self.freq_penalty_spin)
        form.addRow(self.frequency_penalty_label, freq_row)

        self.presence_penalty_label = BodyLabel(self)
        self.pres_penalty_slider = Slider(QtCore.Qt.Orientation.Horizontal, self)
        self.pres_penalty_slider.setRange(*PENALTY_SLIDER_RANGE)
        self.pres_penalty_spin = DoubleSpinBox(self)
        self.pres_penalty_spin.setRange(*PENALTY_SPINBOX_RANGE)
        self.pres_penalty_spin.setSingleStep(PRECISION_SPINBOX_STEP)
        pres_row = QtWidgets.QWidget(self)
        pres_layout = QtWidgets.QHBoxLayout(pres_row)
        pres_layout.setContentsMargins(0, 0, 0, 0)
        pres_layout.addWidget(self.pres_penalty_slider, 1)
        pres_layout.addWidget(self.pres_penalty_spin)
        form.addRow(self.presence_penalty_label, pres_row)

        layout.addLayout(form)

        self.capability_notice_label = BodyLabel(self)
        self.capability_notice_label.setWordWrap(True)
        self.capability_notice_label.setStyleSheet(
            f"color: {GEN_PARAMS_NOTICE_COLOR}; {GEN_PARAMS_NOTICE_STYLE}"
        )
        self.capability_notice_label.hide()
        layout.addWidget(self.capability_notice_label)

        for spinbox in (
            self.budget_spin,
            self.temp_spin,
            self.top_p_spin,
            self.max_tokens_spin,
            self.freq_penalty_spin,
            self.pres_penalty_spin,
        ):
            fix_spin_box_editor(spinbox)
            spinbox.setMinimumWidth(GEN_PARAMS_SPINBOX_MIN_WIDTH)
            spinbox.setMaximumWidth(GEN_PARAMS_SPINBOX_MAX_WIDTH)
        self.level_combo.setMinimumWidth(GEN_PARAMS_COMBO_MIN_WIDTH)
        self.level_combo.setMaximumWidth(GEN_PARAMS_COMBO_MAX_WIDTH)

        self.level_label.hide()
        self.level_row.hide()

    def _refresh_dynamic_localization(self):
        self.budget_spin.setSpecialValueText(
            translate("widget.generation_params.thinking_budget.auto")
        )
        current_level = self.level_combo.currentData() or "high"
        self.level_combo.blockSignals(True)
        self.level_combo.clear()
        self.level_combo.addItem(
            translate(GEMINI_THINKING_LEVEL_KEYS[0]), userData="low"
        )
        self.level_combo.addItem(
            translate(GEMINI_THINKING_LEVEL_KEYS[1]), userData="high"
        )
        index = self.level_combo.findData(current_level)
        if index >= 0:
            self.level_combo.setCurrentIndex(index)
        self.level_combo.blockSignals(False)

        if self.capability_notice_label.isVisible():
            self.show_capability_notice("thoughts_unsupported")

    def _bind_slider_to_spinbox(self, slider: Slider, spinbox: DoubleSpinBox):
        slider.valueChanged.connect(
            lambda value: spinbox.setValue(value / SLIDER_TO_SPINBOX_FACTOR)
        )
        spinbox.valueChanged.connect(
            lambda value: slider.setValue(int(value * SLIDER_TO_SPINBOX_FACTOR))
        )

    def connect_signals(self):
        self._bind_slider_to_spinbox(self.temp_slider, self.temp_spin)
        self._bind_slider_to_spinbox(self.top_p_slider, self.top_p_spin)
        self._bind_slider_to_spinbox(self.freq_penalty_slider, self.freq_penalty_spin)
        self._bind_slider_to_spinbox(self.pres_penalty_slider, self.pres_penalty_spin)
        self.temp_slider.sliderReleased.connect(self._on_param_changed)
        self.top_p_slider.sliderReleased.connect(self._on_param_changed)
        self.freq_penalty_slider.sliderReleased.connect(self._on_param_changed)
        self.pres_penalty_slider.sliderReleased.connect(self._on_param_changed)
        self.use_context_check.toggled.connect(self._on_param_changed)
        self.enable_thinking_check.toggled.connect(self._on_param_changed)
        self.budget_spin.valueChanged.connect(self._on_param_changed)
        self.level_combo.currentIndexChanged.connect(self._on_param_changed)
        self.temp_spin.editingFinished.connect(self._on_param_changed)
        self.top_p_spin.editingFinished.connect(self._on_param_changed)
        self.max_tokens_spin.editingFinished.connect(self._on_param_changed)
        self.freq_penalty_spin.editingFinished.connect(self._on_param_changed)
        self.pres_penalty_spin.editingFinished.connect(self._on_param_changed)

    def set_params(self, params: dict):
        self._updating = True
        defaults = settings.get_default_generation_params()
        self.use_context_check.setChecked(
            params.get("use_content_as_context", defaults["use_content_as_context"])
        )
        self.enable_thinking_check.setChecked(
            params.get("enable_model_thinking", defaults["enable_model_thinking"])
        )
        self.temp_spin.setValue(params.get("temperature", defaults["temperature"]))
        self.top_p_spin.setValue(params.get("top_p", defaults["top_p"]))
        self.max_tokens_spin.setValue(
            params.get("max_output_tokens", defaults["max_output_tokens"])
        )
        self.freq_penalty_spin.setValue(
            params.get("frequency_penalty", defaults["frequency_penalty"])
        )
        self.pres_penalty_spin.setValue(
            params.get("presence_penalty", defaults["presence_penalty"])
        )
        self.budget_spin.setValue(
            int(params.get("thinking_budget_value", defaults["thinking_budget_value"]))
        )
        level = str(params.get("thinking_level", "high")).lower()
        index = self.level_combo.findData(level)
        if index >= 0:
            self.level_combo.setCurrentIndex(index)
        self._updating = False

    @QtCore.Slot()
    def _on_param_changed(self):
        if self._updating:
            return
        params = {
            "use_content_as_context": self.use_context_check.isChecked(),
            "enable_model_thinking": self.enable_thinking_check.isChecked(),
            "temperature": self.temp_spin.value(),
            "top_p": self.top_p_spin.value(),
            "max_output_tokens": self.max_tokens_spin.value(),
            "frequency_penalty": self.freq_penalty_spin.value(),
            "presence_penalty": self.pres_penalty_spin.value(),
        }
        if self._is_gemini_3:
            params["thinking_level"] = self.level_combo.currentData() or "high"
        else:
            params["thinking_budget_value"] = self.budget_spin.value()
        self.params_changed.emit(params)

    def set_connection_type(self, connection_name: str, model_name: str = ""):
        self._updating = True
        self.capability_notice_label.hide()
        logger.debug(
            "Setting GenerationParams for %s (Model: %s)", connection_name, model_name
        )
        conn = next(
            (
                c
                for c in settings.current_settings.get("custom_connections", [])
                if c.get("name") == connection_name
            ),
            None,
        )
        params = settings.get_default_generation_params()
        if conn:
            if model_name:
                configured_models = conn.get("configured_models", [])
                for model_config in configured_models:
                    full_model_id = model_config.get("model_id", "")
                    clean_name = (
                        full_model_id.split("/")[-1]
                        if "/" in full_model_id
                        else full_model_id
                    )
                    if clean_name == model_name or full_model_id == model_name:
                        params = model_config.get(
                            "generation_params",
                            settings.get_default_generation_params(),
                        )
                        break
                else:
                    params = conn.get(
                        "generation_params", settings.get_default_generation_params()
                    )
            else:
                params = conn.get(
                    "generation_params", settings.get_default_generation_params()
                )
        self._is_gemini_3 = "gemini-3" in model_name.lower()
        self.enable_thinking_check.setEnabled(True)
        self.budget_label.setVisible(not self._is_gemini_3)
        self.budget_row.setVisible(not self._is_gemini_3)
        self.level_label.setVisible(self._is_gemini_3)
        self.level_row.setVisible(self._is_gemini_3)
        self.set_params(params)
        self._updating = False
        self._on_param_changed()

    def show_capability_notice(self, capability: str):
        if capability == "thoughts_unsupported":
            self.capability_notice_label.setText(
                translate(
                    "widget.generation_params.capability_notice.thoughts_unsupported"
                )
            )
            UIAnimator.toggle_visibility_animated_vertical(
                self.capability_notice_label, show=True, duration_ms=400
            )
