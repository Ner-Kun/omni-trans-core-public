import logging
from typing import Optional, Callable
from PySide6 import QtWidgets, QtCore
from functools import wraps
from .. import settings
from .dialogs import ManageLanguagesDialog
from .base_widgets import FilterableTableWidget
from .animations import UIAnimator, AnimatedDialog
from ..localization_manager import loc_man, translate, auto_register
from ..utils import DebounceTimer, load_ui, get_model_clean_name
from ..interfaces import IControlWidgetActions, TranslatableItem
from ..notification_manager import (
    NotificationManager,
    NotificationItem,
    NotificationType,
    NOTIFICATION_STYLES,
)

logger = logging.getLogger('CORE_UI.widgets')

# GenerationParamsWidget
GEN_PARAMS_MAIN_SPACING = 10
GEN_PARAMS_NOTICE_COLOR = "#f1fa8c"
GEN_PARAMS_NOTICE_STYLE = "font-style: italic;"
GEN_PARAMS_NOTICE_LEFT_MARGIN = 15
GEN_PARAMS_THINKING_WIDGET_LEFT_MARGIN = 15
GEN_PARAMS_BUDGET_LABEL_MIN_WIDTH = 50
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

# TranslationControlWidget
EDIT_DEBOUNCE_INTERVAL_MS = 1000
EDITING_STATUS_FLASH_DURATION_MS = 800
EDITING_STATUS_FLASH_COLOR = "#f1fa8c"

@auto_register(
    ("", "toolTip", "widget.rpm_status.tooltip"),
)
class RPMStatusWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        load_ui("rpm_status_widget.ui", self, __file__)
        self._height_is_set = False
        self.tableWidget.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.tableWidget.verticalHeader().setVisible(False)
        self.tableWidget.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.tableWidget.setRowCount(1)
        self.tableWidget.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.tableWidget.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        # Set initial form text (will be overridden by update_status later)
        self.model_name_label.setText(translate("widget.rpm_status.form.model_name_label"))
        self.message_label.setText(translate("widget.rpm_status.form.message_label"))
        self.update_status({"message": translate("widget.rpm_status.select_model"), "color": "#FFFFFF"})

    @QtCore.Slot(dict)
    def update_status(self, data: dict):
        if "connections" in data:
            self._update_multi_connection_status(data["connections"])
            return
        if "message" in data:
            self.message_label.setText(data["message"])
            self.message_label.setStyleSheet(f"color: {data.get('color', '#FFFFFF')}; font-weight: bold;")
            self.stackedWidget.setCurrentWidget(self.message_page)
            return

    def _update_multi_connection_status(self, connections_data: list[dict]):
        """Update status for multiple connections."""
        self.stackedWidget.setCurrentWidget(self.table_page)
        count = len(connections_data)
        self.model_name_label.setText(
            translate("widget.rpm_status.multi_connection", count=count)
        )
        all_limits: dict[str, dict[str, int]] = {}
        for conn_info in connections_data:
            status = conn_info.get("status", {})
            limits = status.get("limits", [])
            for limit in limits:
                name = limit.get("name", "")
                if not name:
                    continue
                if name not in all_limits:
                    all_limits[name] = {"current": 0, "total": 0}
                all_limits[name]["current"] += limit.get("current", 0)
                all_limits[name]["total"] += limit.get("total", 0)
        self.tableWidget.setColumnCount(0)
        self.tableWidget.setRowCount(1)
        if not all_limits:
            return
        limit_names = list(all_limits.keys())
        self.tableWidget.setColumnCount(len(limit_names))
        self.tableWidget.setHorizontalHeaderLabels(limit_names)
        rpm_data = None
        for i, name in enumerate(limit_names):
            info = all_limits[name]
            value_text = f"{info['current']} / {info['total']}"
            item = QtWidgets.QTableWidgetItem(value_text)
            item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.tableWidget.setItem(0, i, item)
            if name.upper() == "RPM":
                rpm_data = info
        if not self._height_is_set and self.tableWidget.columnCount() > 0:
            header_height = self.tableWidget.horizontalHeader().sizeHint().height()
            if header_height <= 0:
                header_height = 25
            row_height = self.tableWidget.rowHeight(0)
            if row_height <= 0:
                row_height = 30
            total_height = header_height + row_height + (self.tableWidget.frameWidth() * 2)
            self.tableWidget.setFixedHeight(total_height)
            self.tableWidget.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
            )
            self._height_is_set = True
        if rpm_data:
            current, total = rpm_data.get("current", 0), rpm_data.get("total", 1)
            self.progressBar.setRange(0, total)
            self.progressBar.setValue(current)
            usage_percent = (current / total) * 100 if total > 0 else 0
            self.progressBar.setFormat(f"{usage_percent:.0f}%")
            if usage_percent > 95:
                color = "#ff5555"
            elif usage_percent > 75:
                color = "#f1fa8c"
            else:
                color = "#50fa7b"
            self.progressBar.setStyleSheet(f"""
                QProgressBar {{
                    border: 1px solid #555; border-radius: 4px; text-align: center;
                    background-color: #282a36; color: #f8f8f2; font-weight: bold;
                }}
                QProgressBar::chunk {{ background-color: {color}; border-radius: 3px; }}
            """)
        else:
            self.progressBar.setRange(0, 100)
            self.progressBar.setValue(0)
            self.progressBar.setFormat(translate("widget.rpm_status.rpm_na"))
            self.progressBar.setStyleSheet("""
                QProgressBar {
                    border: 1px solid #555; border-radius: 4px; text-align: center;
                    background-color: #282a36; color: #f8f8f2; font-weight: bold;
                }
            """)

@auto_register(
    ("", "title", "widget.generation_params.title"),
    ("useContentContextCheck", "text", "widget.generation_params.use_content_context"),
    ("useContentContextCheck", "toolTip", "widget.generation_params.use_content_context.tooltip"),
    ("enable_thinking_check", "text", "widget.generation_params.enable_model_thinking"),
    ("enable_thinking_check", "toolTip", "widget.generation_params.enable_model_thinking.tooltip"),
    ("gemini_budget_slider", "toolTip", "widget.generation_params.thinking_budget.tooltip"),
    ("thinking_budget_label_for_layout", "text", "widget.generation_params.thinking_budget.label"),
    ("temperature_label", "text", "widget.generation_params.temperature.label"),
    ("top_p_label", "text", "widget.generation_params.top_p.label"),
    ("max_output_tokens_label", "text", "widget.generation_params.max_output_tokens.label"),
    ("max_tokens_spinbox", "toolTip", "widget.generation_params.max_output_tokens.tooltip"),
    ("frequency_penalty_label", "text", "widget.generation_params.frequency_penalty.label"),
    ("presence_penalty_label", "text", "widget.generation_params.presence_penalty.label"),
    ("gemini_level_combo", "comboKeys", GEMINI_THINKING_LEVEL_KEYS),
)
class GenerationParamsWidget(QtWidgets.QGroupBox):
    params_changed = QtCore.Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.gemini_possible_budget_values = []
        load_ui("generation_params_widget.ui", self, __file__)
        self.thinking_budget_container.hide()
        if hasattr(self, "gemini_level_combo"):
            self.gemini_level_combo.setVisible(False)
            self.gemini_level_combo.setItemData(0, "low")
            self.gemini_level_combo.setItemData(1, "high")
        self._refresh_dynamic_localization()
        self.connect_signals()
        loc_man.language_changed.connect(self._refresh_dynamic_localization)
        logger.debug("GenerationParamsWidget initialized")

    def _update_thinking_budget_visibility(self):
        is_gemini_active = self.thinking_stacked_widget.currentIndex() == 0
        is_thinking_enabled = self.enable_thinking_check.isChecked()
        should_show = is_gemini_active and is_thinking_enabled
        if self.thinking_budget_container.isVisible() != should_show:
            UIAnimator.toggle_visibility_animated_vertical(self.thinking_budget_container, show=should_show)

    def _refresh_dynamic_localization(self):
        self._update_budget_label(self.gemini_budget_slider.value())
        if self.capability_notice_label.isVisible():
            self.show_capability_notice('thoughts_unsupported')

    def _bind_slider_to_spinbox(self, slider: QtWidgets.QSlider, spinbox: QtWidgets.QDoubleSpinBox):
        """Bind a slider to a spinbox with bidirectional synchronization."""
        slider.valueChanged.connect(lambda v: spinbox.setValue(v / SLIDER_TO_SPINBOX_FACTOR))
        spinbox.valueChanged.connect(lambda v: slider.setValue(int(v * SLIDER_TO_SPINBOX_FACTOR)))

    def connect_signals(self):
        self._bind_slider_to_spinbox(self.temp_slider, self.temp_spinbox)
        self._bind_slider_to_spinbox(self.top_p_slider, self.top_p_spinbox)
        self._bind_slider_to_spinbox(self.freq_penalty_slider, self.freq_penalty_spinbox)
        self._bind_slider_to_spinbox(self.pres_penalty_slider, self.pres_penalty_spinbox)
        self.temp_slider.sliderReleased.connect(self._on_param_changed)
        self.top_p_slider.sliderReleased.connect(self._on_param_changed)
        self.freq_penalty_slider.sliderReleased.connect(self._on_param_changed)
        self.pres_penalty_slider.sliderReleased.connect(self._on_param_changed)
        self.useContentContextCheck.toggled.connect(self._on_param_changed)
        self.enable_thinking_check.toggled.connect(self._update_thinking_budget_visibility)
        self.enable_thinking_check.toggled.connect(self._on_param_changed)
        self.gemini_budget_slider.valueChanged.connect(self._update_budget_label)
        self.gemini_budget_slider.sliderReleased.connect(self._on_param_changed)
        if hasattr(self, "gemini_level_combo"):
            self.gemini_level_combo.currentTextChanged.connect(self._on_param_changed)
        self.temp_spinbox.editingFinished.connect(self._on_param_changed)
        self.top_p_spinbox.editingFinished.connect(self._on_param_changed)
        self.max_tokens_spinbox.editingFinished.connect(self._on_param_changed)
        self.freq_penalty_spinbox.editingFinished.connect(self._on_param_changed)
        self.pres_penalty_spinbox.editingFinished.connect(self._on_param_changed)

    def set_params(self, params: dict):
        self.blockSignals(True)
        defaults = settings.get_default_generation_params()
        self.useContentContextCheck.setChecked(params.get("use_content_as_context", defaults["use_content_as_context"]))
        is_thinking_enabled = params.get("enable_model_thinking", defaults["enable_model_thinking"])
        self.enable_thinking_check.setChecked(is_thinking_enabled)
        self.temp_spinbox.setValue(params.get("temperature", defaults["temperature"]))
        self.top_p_spinbox.setValue(params.get("top_p", defaults["top_p"]))
        self.max_tokens_spinbox.setValue(params.get("max_output_tokens", defaults["max_output_tokens"]))
        self.freq_penalty_spinbox.setValue(params.get("frequency_penalty", defaults["frequency_penalty"]))
        self.pres_penalty_spinbox.setValue(params.get("presence_penalty", defaults["presence_penalty"]))
        if self.thinking_stacked_widget.currentIndex() == 0:
            budget_value = params.get(
                "thinking_budget_value", defaults["thinking_budget_value"]
            )
            try:
                target_index = self.gemini_possible_budget_values.index(budget_value)
                self.gemini_budget_slider.setValue(target_index)
            except ValueError:
                self.gemini_budget_slider.setValue(0)
            self._update_budget_label(self.gemini_budget_slider.value())

            if hasattr(self, "gemini_level_combo"):
                level_value = params.get(
                    "thinking_level", defaults.get("thinking_level", "high")
                )
                level_index = self.gemini_level_combo.findData(str(level_value).lower())
                if level_index >= 0:
                    self.gemini_level_combo.setCurrentIndex(level_index)

        self.blockSignals(False)

    @QtCore.Slot()
    def _on_param_changed(self):
        params = {
            "use_content_as_context": self.useContentContextCheck.isChecked(),
            "enable_model_thinking": self.enable_thinking_check.isChecked(),
            "temperature": self.temp_spinbox.value(),
            "top_p": self.top_p_spinbox.value(),
            "max_output_tokens": self.max_tokens_spinbox.value(),
            "frequency_penalty": self.freq_penalty_spinbox.value(),
            "presence_penalty": self.pres_penalty_spinbox.value(),}
        if self.thinking_stacked_widget.currentIndex() == 0:
            current_index = self.gemini_budget_slider.value()
            if 0 <= current_index < len(self.gemini_possible_budget_values):
                params["thinking_budget_value"] = self.gemini_possible_budget_values[
                    current_index
                ]
            else:
                params["thinking_budget_value"] = -1

            if hasattr(self, "gemini_level_combo"):
                params["thinking_level"] = self.gemini_level_combo.currentData() or "high"
        else:
            params["thinking_budget_value"] = -1
            params["thinking_level"] = "high"

        logger.debug("_on_param_changed emitting params_changed: temp=%s, max_tokens=%s", params.get('temperature'), params.get('max_output_tokens'))
        self.params_changed.emit(params)

    def _update_budget_label(self, value):
        if 0 <= value < len(self.gemini_possible_budget_values):
            budget = self.gemini_possible_budget_values[value]
            display_text = translate("widget.generation_params.thinking_budget.auto") if budget == -1 else str(budget)
            self.gemini_budget_label.setText(display_text)

    def _update_gemini_thinking_options(self, model_name: str, generation_params: dict):
        model_name_lower = model_name.lower()
        
        is_gemini_3 = "gemini-3" in model_name_lower
        
        if hasattr(self, "gemini_level_combo"):
            self.gemini_level_combo.setVisible(is_gemini_3)
            self.gemini_budget_slider.setVisible(not is_gemini_3)
            self.gemini_budget_label.setVisible(not is_gemini_3)
            
            if is_gemini_3:
                loc_man.register(self.thinking_budget_label_for_layout, "text", "widget.generation_params.thinking_level.label")
            else:
                loc_man.register(self.thinking_budget_label_for_layout, "text", "widget.generation_params.thinking_budget.label")
        
        is_pro_2 = "pro" in model_name_lower and not is_gemini_3
        max_budget = GEMINI_PRO_MAX_BUDGET if is_pro_2 else GEMINI_FLASH_MAX_BUDGET
        
        budget_range = range(GEMINI_BUDGET_STEP, max_budget + 1, GEMINI_BUDGET_STEP)
        self.gemini_possible_budget_values = [-1] + list(budget_range)
        
        self.gemini_budget_slider.blockSignals(True)
        self.gemini_budget_slider.setRange(0, len(self.gemini_possible_budget_values) - 1)
        self.gemini_budget_slider.blockSignals(False)

        if is_pro_2:
            self.enable_thinking_check.setChecked(True)
            self.enable_thinking_check.setEnabled(False)
        else:
            self.enable_thinking_check.setEnabled(True)
            self.enable_thinking_check.setChecked(generation_params.get("enable_model_thinking", True))
        
        self.set_params(generation_params)
        
        if not is_gemini_3:
            self._update_budget_label(self.gemini_budget_slider.value())

    def set_connection_type(self, connection_name: str, model_name: str = ""):
        self.blockSignals(True)
        self.capability_notice_label.hide()
        is_gemini = (connection_name == "Google Gemini")
        if is_gemini:
            logger.debug("Setting GenerationParams for Gemini (Model: %s)", model_name)
            self.thinking_stacked_widget.setCurrentIndex(0)
            params = settings.current_settings.get("gemini_generation_params", settings.get_default_generation_params())
            self._update_gemini_thinking_options(model_name, params)
        else:
            logger.debug("Setting GenerationParams for Custom Connection: %s (Model: %s)", connection_name, model_name)
            self.thinking_stacked_widget.setCurrentIndex(1)
            conn = next((c for c in settings.current_settings.get("custom_connections", []) if c.get("name") == connection_name), None)
            params = settings.get_default_generation_params()
            if conn:
                # Try to find model-specific params first
                if model_name:
                    configured_models = conn.get("configured_models", [])
                    for model_config in configured_models:
                        full_model_id = model_config.get("model_id", "")
                        clean_name = full_model_id.split('/')[-1] if '/' in full_model_id else full_model_id
                        if clean_name == model_name or full_model_id == model_name:
                            params = model_config.get("generation_params", settings.get_default_generation_params())
                            logger.debug("Loaded model-specific params for '%s'", model_name)
                            break
                    else:
                        # Model not found in configured_models, fallback to connection params
                        params = conn.get("generation_params", settings.get_default_generation_params())
                        logger.debug("Model '%s' not found in configured_models, using connection params", model_name)
                else:
                    # No model specified, use connection-level params
                    params = conn.get("generation_params", settings.get_default_generation_params())
            self.enable_thinking_check.setEnabled(True)
            self.set_params(params)
        if is_gemini:
            self._update_budget_label(self.gemini_budget_slider.value())
        self.blockSignals(False)
        self._update_thinking_budget_visibility()
        self._on_param_changed()

    def show_capability_notice(self, capability: str):
        if capability == 'thoughts_unsupported':
            notice_text = translate("widget.generation_params.capability_notice.thoughts_unsupported")
            self.capability_notice_label.setText(notice_text)
            UIAnimator.toggle_visibility_animated_vertical(self.capability_notice_label, show=True, duration_ms=400)

@auto_register(
    ("search_input", "placeholderText", "widget.searchable_table.search_placeholder"),
)
class DataTableWidget(QtWidgets.QWidget):
    selection_changed = QtCore.Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._columns_config = []
        self._data = []
        self._unique_id_key = None
        self._id_to_row_map = {}
        self._row_to_id_map = {}
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.search_input = QtWidgets.QLineEdit()
        self.table = FilterableTableWidget()
        layout.addWidget(self.search_input)
        layout.addWidget(self.table)
        self.search_input.textChanged.connect(self.table.filter)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

    def configure(self, columns: list[dict]):
        self._columns_config = columns
        self.table.setColumnCount(len(columns))
        self._apply_column_headers()
        header_view = self.table.horizontalHeader()
        for i, col_config in enumerate(columns):
            resize_mode = col_config.get('resize_mode', QtWidgets.QHeaderView.ResizeMode.Interactive)
            header_view.setSectionResizeMode(i, resize_mode)

    def _apply_column_headers(self):
        """Apply translated headers from column config."""
        headers = []
        for col in self._columns_config:
            if "header_key" in col:
                headers.append(translate(col["header_key"]))
            else:
                headers.append(col.get("header", ""))
        self.table.setHorizontalHeaderLabels(headers)

    def retranslate_ui(self):
        """Re-apply column headers with current translations."""
        self._apply_column_headers()

    def set_data(self, data: list[dict], unique_id_key: str):
        self._data = data
        self._unique_id_key = unique_id_key
        self._id_to_row_map.clear()
        self._row_to_id_map.clear()
        self.table.setRowCount(0)
        if not data:
            return
        self.table.setRowCount(len(data))
        try:
            self.table.setUpdatesEnabled(False)
            for row_idx, row_data in enumerate(data):
                row_id = row_data.get(unique_id_key)
                if row_id is None:
                    logger.warning("DataTableWidget.set_data: row at index %d has no '%s' key, skipping", row_idx, unique_id_key)
                    continue
                self._id_to_row_map[row_id] = row_idx
                self._row_to_id_map[row_idx] = row_id
                full_search_text_parts = []
                for col_idx, col_config in enumerate(self._columns_config):
                    data_key = col_config.get('key')
                    if not data_key:
                        continue
                    cell_value = str(row_data.get(data_key, ''))
                    item = QtWidgets.QTableWidgetItem(cell_value)
                    self.table.setItem(row_idx, col_idx, item)
                    full_search_text_parts.append(cell_value)
                self.table.set_row_hidden_data(row_idx, " ".join(full_search_text_parts))
        finally:
            self.table.setUpdatesEnabled(True)

    def update_row_by_id(self, row_id, new_row_data: dict):
        row_idx = self._id_to_row_map.get(row_id)
        if row_idx is None:
            return
        self._data[row_idx].update(new_row_data)
        full_search_text_parts = []
        for col_idx, col_config in enumerate(self._columns_config):
            data_key = col_config.get('key')
            if not data_key:
                continue
            cell_value = str(self._data[row_idx].get(data_key, ''))
            item = self.table.item(row_idx, col_idx)
            if item:
                item.setText(cell_value)
            else:
                self.table.setItem(row_idx, col_idx, QtWidgets.QTableWidgetItem(cell_value))
            full_search_text_parts.append(cell_value)
        self.table.set_row_hidden_data(row_idx, " ".join(full_search_text_parts))

    def get_selected_rows_data(self) -> list[dict]:
        selected_rows_indices = {idx.row() for idx in self.table.selectedIndexes()}
        if not selected_rows_indices:
            return []
        selected_data = []
        for row_idx in sorted(list(selected_rows_indices)):
            row_id = self._row_to_id_map.get(row_idx)
            if row_id:
                selected_data.append(self._data[row_idx])
        return selected_data

    def flash_row_by_id(self, row_ids: str | list[str], color: str | None = None):
        if isinstance(row_ids, str):
            ids_to_process = [row_ids]
        else:
            ids_to_process = row_ids
        row_indices = []
        for row_id in ids_to_process:
            row_idx = self._id_to_row_map.get(row_id)
            if row_idx is not None:
                row_indices.append(row_idx)
        if not row_indices:
            return
        if color:
            UIAnimator.flash_table_row(self.table, row_indices, highlight_color_hex=color)
        else:
            UIAnimator.flash_table_row(self.table, row_indices)

    def scroll_to_row_by_id(self, row_id):
        row_idx = self._id_to_row_map.get(row_id)
        if row_idx is not None:
            item = self.table.item(row_idx, 0)
            if item:
                self.table.scrollToItem(item, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)

    @QtCore.Slot()
    def _on_selection_changed(self):
        selected_data = self.get_selected_rows_data()
        self.selection_changed.emit(selected_data)

@auto_register(
    ("", "title", "widget.control.group_title"),
    ("original_text_label", "text", "widget.control.original_label"),
    ("trans_edit", "placeholderText", "widget.control.edit_placeholder"),
    ("regenerate_btn", "text", "widget.control.button_regenerate"),
    ("translate_selected_btn", "text", "widget.control.button_translate_selected"),
    ("translate_selected_btn", "toolTip", "widget.control.button_translate_tooltip_selected"),
    ("translate_all_btn", "text", "widget.control.button_translate_all"),
    ("translate_all_btn", "toolTip", "widget.control.button_translate_tooltip_all"),
    ("delete_selected_btn", "text", "widget.control.button_delete_selected"),
    ("delete_selected_btn", "toolTip", "widget.control.button_delete_tooltip_selected"),
    ("delete_all_btn", "text", "widget.control.button_delete_all"),
    ("delete_all_btn", "toolTip", "widget.control.button_delete_tooltip_all"),
)
class TranslationControlWidget(QtWidgets.QGroupBox):
    item_edited = QtCore.Signal(str, str)

    def __init__(self, actions_handler: IControlWidgetActions, parent=None):
        super().__init__(parent)
        self.actions_handler = actions_handler
        self.current_item_id = None
        self.current_translation_in_editor = None
        self.debounce_timer = DebounceTimer(self._apply_edited_translation, EDIT_DEBOUNCE_INTERVAL_MS, self)
        self._init_ui()
        self._connect_signals()
        loc_man.language_changed.connect(self._refresh_dynamic_localization)
        initial_lang = settings.current_settings.get("selected_target_language", "")
        self.set_active_language(initial_lang)

    def _init_ui(self):
        layout = QtWidgets.QFormLayout(self)
        orig_key_layout = QtWidgets.QHBoxLayout()
        orig_key_layout.setContentsMargins(0, 0, 0, 0)
        self.orig_label = QtWidgets.QLabel()
        self.orig_label.setWordWrap(True)
        orig_key_layout.addWidget(self.orig_label)
        orig_key_layout.addStretch(1)
        self.save_status_label = QtWidgets.QLabel()
        self.save_status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        orig_key_layout.addWidget(self.save_status_label)
        self.original_text_label = QtWidgets.QLabel()
        layout.addRow(self.original_text_label, orig_key_layout)
        self.trans_edit = QtWidgets.QLineEdit()
        self.translation_label = QtWidgets.QLabel()
        layout.addRow(self.translation_label, self.trans_edit)
        action_buttons_layout = QtWidgets.QHBoxLayout()
        self.regenerate_btn = QtWidgets.QPushButton()
        translate_button_layout = QtWidgets.QHBoxLayout()
        translate_button_layout.setSpacing(0)
        translate_button_layout.setContentsMargins(0, 0, 0, 0)
        self.translate_selected_btn = QtWidgets.QPushButton()
        self.translate_selected_btn.setStyleSheet("border-top-right-radius: 0px; border-bottom-right-radius: 0px;")
        self.translate_all_btn = QtWidgets.QPushButton()
        self.translate_all_btn.setStyleSheet("border-top-left-radius: 0px; border-bottom-left-radius: 0px;")
        self.translate_all_btn.setFixedWidth(50)
        translate_button_layout.addWidget(self.translate_selected_btn)
        translate_button_layout.addWidget(self.translate_all_btn)
        delete_button_layout = QtWidgets.QHBoxLayout()
        delete_button_layout.setSpacing(0)
        delete_button_layout.setContentsMargins(0, 0, 0, 0)
        self.delete_selected_btn = QtWidgets.QPushButton()
        self.delete_selected_btn.setStyleSheet("border-top-right-radius: 0px; border-bottom-right-radius: 0px;")
        self.delete_all_btn = QtWidgets.QPushButton()
        self.delete_all_btn.setStyleSheet("border-top-left-radius: 0px; border-bottom-left-radius: 0px;")
        self.delete_all_btn.setFixedWidth(50)
        delete_button_layout.addWidget(self.delete_selected_btn)
        delete_button_layout.addWidget(self.delete_all_btn)
        action_buttons_layout.addWidget(self.regenerate_btn)
        action_buttons_layout.addStretch()
        action_buttons_layout.addLayout(translate_button_layout)
        action_buttons_layout.addStretch()
        action_buttons_layout.addLayout(delete_button_layout)
        layout.addRow(action_buttons_layout)
        self.clear_selection()
        self.translate_all_btn.setEnabled(False)
        self.delete_all_btn.setEnabled(False)

    def _require_items(requirement_type: str):
        def decorator(func):
            @wraps(func)
            def wrapper(self, *args, **kwargs):
                items = []
                if requirement_type == 'selected':
                    items = self.actions_handler.get_selected_items()
                    if not items:
                        title = translate("widget.control.error.no_selection.title")
                        text = translate("widget.control.error.no_selection.text")
                        self.actions_handler.show_info_message(title, text)
                        return
                elif requirement_type == 'all':
                    items = self.actions_handler.get_all_items()
                    if not items:
                        title = translate("widget.control.error.no_data.title")
                        text = translate("widget.control.error.no_data.text")
                        self.actions_handler.show_info_message(title, text)
                        return
                return func(self, items, *args, **kwargs)
            return wrapper
        return decorator

    def _refresh_dynamic_localization(self):
        if self.current_item_id is None:
            self.save_status_label.setText(translate("widget.control.status_no_selection"))
        initial_lang = settings.current_settings.get("selected_target_language", "")
        self.set_active_language(initial_lang)

    def _connect_signals(self):
        self.trans_edit.textChanged.connect(self._on_text_changed)
        self.trans_edit.editingFinished.connect(self.on_before_save)
        self.actions_handler.data_availability_changed.connect(self.translate_all_btn.setEnabled)
        self.actions_handler.data_availability_changed.connect(self.delete_all_btn.setEnabled)
        self.regenerate_btn.clicked.connect(self._on_regenerate)
        self.translate_selected_btn.clicked.connect(self._on_translate_selected)
        self.translate_all_btn.clicked.connect(self._on_translate_all)
        self.delete_selected_btn.clicked.connect(self._on_delete)
        self.delete_all_btn.clicked.connect(self._on_delete_all)

    def set_active_language(self, lang_name: str):
        if lang_name:
            self.translation_label.setText(translate("widget.control.translation_label_template", lang_name=lang_name))
        else:
            self.translation_label.setText(translate("widget.control.translation_label_default"))

    def block_all_signals(self, block: bool):
        self.trans_edit.blockSignals(block)
        self.regenerate_btn.blockSignals(block)
        self.translate_selected_btn.blockSignals(block)
        self.translate_all_btn.blockSignals(block)
        self.delete_selected_btn.blockSignals(block)
        self.delete_all_btn.blockSignals(block)

    def set_data(self, item_id: str, original_text: str, translated_text: str):
        self.debounce_timer.cancel()
        self.current_item_id = item_id
        self.current_translation_in_editor = translated_text
        self.block_all_signals(True)
        self.orig_label.setText(original_text)
        self.trans_edit.setText(translated_text)
        self.regenerate_btn.setEnabled(True)
        self.delete_selected_btn.setEnabled(True)
        self.translate_selected_btn.setEnabled(True)
        self.trans_edit.setEnabled(True)
        self.block_all_signals(False)
        UIAnimator.flash_status_label(self.save_status_label, translate("widget.control.status_saved"))

    def clear_selection(self):
        self.debounce_timer.cancel()
        self.current_item_id = None
        self.current_translation_in_editor = None
        self.block_all_signals(True)
        self.orig_label.clear()
        self.trans_edit.clear()
        self.regenerate_btn.setEnabled(False)
        self.delete_selected_btn.setEnabled(False)
        self.translate_selected_btn.setEnabled(False)
        self.trans_edit.setEnabled(False)
        self.save_status_label.setText(translate("widget.control.status_no_selection"))
        self.block_all_signals(False)

    def update_item_display(self, item_id: str, new_text: str):
        if self.current_item_id == item_id:
            self.trans_edit.blockSignals(True)
            self.trans_edit.setText(new_text)
            self.trans_edit.blockSignals(False)
            self.current_translation_in_editor = new_text
            UIAnimator.flash_status_label(self.save_status_label, translate("widget.control.status_saved"))

    @QtCore.Slot()
    def on_before_save(self):
        self.debounce_timer.force_run()
    
    @QtCore.Slot()
    def _on_text_changed(self):
        if self.current_item_id is not None:
            UIAnimator.flash_status_label(
                self.save_status_label,
                translate("widget.control.status_editing"),
                color=EDITING_STATUS_FLASH_COLOR,
                duration_ms=EDITING_STATUS_FLASH_DURATION_MS)
            self.debounce_timer.trigger()

    @QtCore.Slot()
    def _apply_edited_translation(self):
        if self.current_item_id is None:
            return
        new_text = self.trans_edit.text().strip()
        if new_text != self.current_translation_in_editor:
            logger.debug("Translation edited for item '%s'", self.current_item_id)
            self.current_translation_in_editor = new_text
            self.item_edited.emit(self.current_item_id, new_text)
            UIAnimator.flash_status_label(self.save_status_label, translate("widget.control.status_saved"))

    @QtCore.Slot()
    @_require_items('selected')
    def _on_translate_selected(self, items: list[TranslatableItem]):
        self.actions_handler.handle_translation_request(items, force_regen=False)

    @QtCore.Slot()
    @_require_items('all')
    def _on_translate_all(self, items: list[TranslatableItem]):
        self.actions_handler.handle_translation_request(items, force_regen=False)

    @QtCore.Slot()
    @_require_items('selected')
    def _on_regenerate(self, items: list[TranslatableItem]):
        self.actions_handler.handle_translation_request(items, force_regen=True)

    @QtCore.Slot()
    @_require_items('selected')
    def _on_delete(self, items: list[TranslatableItem]):
        self.actions_handler.handle_deletion_request(items)
        
    @QtCore.Slot()
    @_require_items('all')
    def _on_delete_all(self, items: list[TranslatableItem]):
        self.actions_handler.handle_deletion_request(items)

@auto_register(
    ("manage_button", "text", "widget.language.manage_button"),
)
class _BaseLanguageWidget(QtWidgets.QGroupBox):
    language_changed = QtCore.Signal(str)
    def __init__(self, title_key: str, lang_type: str, parent=None):
        super().__init__(parent)
        if lang_type not in ["source", "target"]:
            raise ValueError("lang_type must be 'source' or 'target'")
        self.title_key = title_key
        self.lang_type = lang_type
        self.config_key = "available_source_languages" if lang_type == "source" else "target_languages"
        self.selected_lang_key = "selected_source_language" if lang_type == "source" else "selected_target_language"
        self.init_ui()
        loc_man.register(self, "title", self.title_key)
        self.connect_signals()
        self.update_language_combo()
        loc_man.language_changed.connect(self.update_language_combo)

    def init_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        self.combo = QtWidgets.QComboBox()
        self.manage_button = QtWidgets.QPushButton()
        layout.addWidget(self.combo)
        layout.addWidget(self.manage_button)

    def connect_signals(self):
        self.combo.currentTextChanged.connect(self._on_language_change)
        self.manage_button.clicked.connect(self._open_manage_dialog)

    def update_language_combo(self):
        self.combo.blockSignals(True)
        self.combo.clear()
        languages = settings.current_settings.get(self.config_key, [])
        if languages:
            self.combo.addItems(languages)
            selected_lang = settings.current_settings.get(self.selected_lang_key, "")
            if selected_lang and selected_lang in languages:
                self.combo.setCurrentText(selected_lang)
            elif languages:
                self.combo.setCurrentIndex(0)
        else:
            placeholder_key = f"widget.language.no_languages_placeholder.{self.lang_type}"
            self.combo.setPlaceholderText(translate(placeholder_key))
            settings.current_settings[self.selected_lang_key] = ""
        self.combo.blockSignals(False)
        self._on_language_change(self.combo.currentText())

    @QtCore.Slot(str)
    def _on_language_change(self, lang_name: str):
        current_selection = settings.current_settings.get(self.selected_lang_key)
        if current_selection != lang_name:
            settings.current_settings[self.selected_lang_key] = lang_name
            settings.save_settings()
            logger.info("Selected %s language changed to: '%s'", self.lang_type, lang_name)
        self.language_changed.emit(lang_name)

    @QtCore.Slot()
    def _open_manage_dialog(self):
        dialog = ManageLanguagesDialog(self.lang_type.capitalize(), self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.update_language_combo()
            
class SourceLanguageWidget(_BaseLanguageWidget):
    def __init__(self, parent=None):
        super().__init__("widget.language.source_title", "source", parent)

class TargetLanguageWidget(_BaseLanguageWidget):
    def __init__(self, parent=None):
        super().__init__("widget.language.target_title", "target", parent)

@auto_register(
    ("", "title", "widget.connection_selection.title"),
    ("connection_combo", "toolTip", "widget.connection_selection.connection_combo.tooltip"),
    ("model_combo", "toolTip", "widget.connection_selection.model_combo.tooltip"),
)
class ConnectionSelectionWidget(QtWidgets.QGroupBox):
    connection_changed = QtCore.Signal(str)
    model_changed = QtCore.Signal(str, str)

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        layout = QtWidgets.QHBoxLayout(self)
        self.connection_combo = QtWidgets.QComboBox()
        self.model_combo = QtWidgets.QComboBox()
        layout.addWidget(self.connection_combo, 2)
        layout.addWidget(self.model_combo, 3)
        self.connection_combo.currentTextChanged.connect(self._on_connection_changed)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)

    def update_connections(self):
        self.connection_combo.blockSignals(True)
        self.connection_combo.clear()
        all_connections = self.main_window.get_available_connection_names()
        if "Google Gemini" in all_connections:
            self.connection_combo.addItem("Google Gemini")
        custom_connections = [name for name in all_connections if name != "Google Gemini"]
        if custom_connections:
            self.connection_combo.insertSeparator(self.connection_combo.count())
            self.connection_combo.addItems(custom_connections)
        active_connection = self.main_window.get_active_connection_name()
        if self.connection_combo.findText(active_connection) != -1:
            self.connection_combo.setCurrentText(active_connection)
        elif self.connection_combo.count() > 0:
            self.connection_combo.setCurrentIndex(0)
        self.connection_combo.blockSignals(False)
        self._on_connection_changed(self.connection_combo.currentText())

    @QtCore.Slot(str)
    def _on_connection_changed(self, connection_name: str):
        if not connection_name:
            self.model_combo.clear()
            return
        self.main_window.set_active_connection_name(connection_name)
        self.connection_changed.emit(connection_name)
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        last_used_model = settings.current_settings.get("active_model_for_connection", {}).get(connection_name)
        if connection_name == "Google Gemini":
            available_models = settings.current_settings.get("available_gemini_models", [])
            gemini_default = settings.current_settings.get("gemini_model")
            if available_models:
                self.model_combo.addItems(available_models)
            elif gemini_default and gemini_default not in available_models:
                self.model_combo.addItem(gemini_default)
            target_model = last_used_model or gemini_default
            if self.model_combo.findText(target_model) != -1:
                self.model_combo.setCurrentText(target_model)
        else:
            conn = next((c for c in settings.current_settings.get("custom_connections", []) if c.get("name") == connection_name), None)
            if conn:
                configured_models = conn.get("configured_models", [])
                if configured_models:
                    for model_config in configured_models:
                        full_model_id = model_config.get("model_id")
                        if full_model_id:
                            clean_name = full_model_id.split('/')[-1] if '/' in full_model_id else full_model_id
                            self.model_combo.addItem(clean_name, full_model_id)
                    if last_used_model:
                        index = self.model_combo.findData(last_used_model)
                        if index != -1:
                            self.model_combo.setCurrentIndex(index)
                        elif self.model_combo.count() > 0:
                            self.model_combo.setCurrentIndex(0)
                    elif self.model_combo.count() > 0:
                        self.model_combo.setCurrentIndex(0)
        self.model_combo.blockSignals(False)
        if self.model_combo.count() > 0:
            self._on_model_changed(self.model_combo.currentText())
        else:
            self.model_changed.emit(connection_name, "")

    @QtCore.Slot(str)
    def _on_model_changed(self, displayed_text: str):
        if not displayed_text:
            active_conn_name = self.connection_combo.currentText()
            self.model_changed.emit(active_conn_name, "")
            return
        active_conn_name = self.connection_combo.currentText()
        model_id_to_use = self.model_combo.currentData() or displayed_text
        if "active_model_for_connection" not in settings.current_settings:
            settings.current_settings["active_model_for_connection"] = {}
        settings.current_settings["active_model_for_connection"][active_conn_name] = model_id_to_use
        logger.debug("Active model for '%s' set to '%s'.", active_conn_name, model_id_to_use)
        self.model_changed.emit(active_conn_name, model_id_to_use)
        
@auto_register(
    ("", "title", "widget.multi_connection.title"),
    ("_select_header_label", "text", "widget.multi_connection.select_header"),
    ("_connection_header_label", "text", "widget.multi_connection.connection_header"),
    ("_model_header_label", "text", "widget.multi_connection.model_header"),
    ("_select_all_btn", "text", "widget.multi_connection.select_all"),
    ("_deselect_all_btn", "text", "widget.multi_connection.deselect_all"),
)
class MultiConnectionTable(QtWidgets.QGroupBox):
    """
    Table widget for selecting multiple custom connections with model selection.
    
    Structure:
    - Row 0: Radio button for Google Gemini (mutually exclusive with custom)
    - Row 1..N: Checkboxes for each custom connection + model dropdown
    """
    connections_changed = QtCore.Signal(list)      # Emits list of (conn_name, model_name) tuples
    row_clicked = QtCore.Signal(str, str)          # Emits (conn_name, model_name) for params display
    model_changed = QtCore.Signal(str, str)        # Emits (conn_name, new_model_id)

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self._row_widgets: list[dict] = []  # [{"checkbox": QCheckBox, "combo": QComboBox, "conn_name": str}, ...]
        self._gemini_radio: QtWidgets.QRadioButton | None = None
        self._gemini_model_combo: QtWidgets.QComboBox | None = None
        self._gemini_selected: bool = False
        self._block_signals: bool = False
        self._selected_row_widget: QtWidgets.QWidget | None = None
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # Header row
        header_layout = QtWidgets.QHBoxLayout()
        self._select_header_label = QtWidgets.QLabel()
        self._connection_header_label = QtWidgets.QLabel()
        self._model_header_label = QtWidgets.QLabel()
        header_layout.addWidget(self._select_header_label, 1)
        header_layout.addWidget(self._connection_header_label, 3)
        header_layout.addWidget(self._model_header_label, 4)
        main_layout.addLayout(header_layout)

        # Scroll area for rows
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll_area.setMinimumHeight(80)
        self._rows_container = QtWidgets.QWidget()
        self._rows_layout = QtWidgets.QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        scroll_area.setWidget(self._rows_container)
        main_layout.addWidget(scroll_area)

        # Bottom buttons
        buttons_layout = QtWidgets.QHBoxLayout()
        self._select_all_btn = QtWidgets.QPushButton()
        self._deselect_all_btn = QtWidgets.QPushButton()
        self._select_all_btn.clicked.connect(self._select_all_custom)
        self._deselect_all_btn.clicked.connect(self._deselect_all_custom)
        buttons_layout.addStretch()
        buttons_layout.addWidget(self._select_all_btn)
        buttons_layout.addWidget(self._deselect_all_btn)
        main_layout.addLayout(buttons_layout)

    def _clear_rows(self):
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._row_widgets.clear()
        self._gemini_radio = None
        self._gemini_model_combo = None
        self._selected_row_widget = None

    def update_connections(self, restore_state: bool = False):
        self._block_signals = True
        self._clear_rows()

        gemini_row = QtWidgets.QWidget()
        gemini_layout = QtWidgets.QHBoxLayout(gemini_row)
        gemini_layout.setContentsMargins(0, 0, 0, 0)
        gemini_layout.setSpacing(4)

        self._gemini_radio = QtWidgets.QRadioButton()
        self._gemini_radio.setToolTip(translate("widget.multi_connection.gemini_radio.tooltip"))
        gemini_layout.addWidget(self._gemini_radio, 1)

        gemini_label = QtWidgets.QLabel("Google Gemini")
        gemini_layout.addWidget(gemini_label, 3)

        self._gemini_model_combo = QtWidgets.QComboBox()
        self._gemini_model_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        gemini_layout.addWidget(self._gemini_model_combo, 4)

        self._rows_layout.addWidget(gemini_row)

        available_models = settings.current_settings.get("available_gemini_models", [])
        gemini_default = settings.current_settings.get("gemini_model")
        if available_models:
            self._gemini_model_combo.addItems(available_models)
        elif gemini_default:
            self._gemini_model_combo.addItem(gemini_default)
        last_gemini_model = settings.current_settings.get("active_model_for_connection", {}).get("Google Gemini")
        target_model = last_gemini_model or gemini_default
        if target_model and self._gemini_model_combo.findText(target_model) != -1:
            self._gemini_model_combo.setCurrentText(target_model)

        self._gemini_radio.toggled.connect(self._on_gemini_radio_toggled)
        self._gemini_model_combo.currentTextChanged.connect(self._on_gemini_model_changed)

        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setFrameShadow(QtWidgets.QFrame.Sunken)
        self._rows_layout.addWidget(sep)

        # Custom connections
        custom_connections = settings.current_settings.get("custom_connections", [])
        active_model_for_connection = settings.current_settings.get("active_model_for_connection", {})

        for conn in custom_connections:
            conn_name = conn.get("name", "")
            if not conn_name:
                continue

            row_widget = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)

            checkbox = QtWidgets.QCheckBox()
            row_layout.addWidget(checkbox, 1)

            conn_label = QtWidgets.QLabel(conn_name)
            row_layout.addWidget(conn_label, 3)

            model_combo = QtWidgets.QComboBox()
            model_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            configured_models = conn.get("configured_models", [])
            for model_config in configured_models:
                full_model_id = model_config.get("model_id", "")
                if full_model_id:
                    model_combo.addItem(get_model_clean_name(full_model_id), full_model_id)

            last_model = active_model_for_connection.get(conn_name)
            if last_model:
                idx = model_combo.findData(last_model)
                if idx != -1:
                    model_combo.setCurrentIndex(idx)
            elif model_combo.count() > 0:
                model_combo.setCurrentIndex(0)

            row_layout.addWidget(model_combo, 4)
            self._rows_layout.addWidget(row_widget)

            row_data = {
                "checkbox": checkbox,
                "combo": model_combo,
                "conn_name": conn_name,
                "row_widget": row_widget,
            }
            self._row_widgets.append(row_data)

            # Highlight row on click
            row_widget.mousePressEvent = lambda event, rd=row_data: self._on_row_clicked(rd)
            checkbox.toggled.connect(lambda checked, rd=row_data: self._on_checkbox_toggled(rd, checked))
            model_combo.currentTextChanged.connect(lambda text, rd=row_data: self._on_model_combo_changed(rd, text))

        # Add stretch at bottom
        self._rows_layout.addStretch()

        # Восстановить состояние ТОЛЬКО если явно запрошено
        if restore_state:
            active_connections_list = settings.current_settings.get("active_connections_list", [])
            active_conn_names = {conn_name for conn_name, _ in active_connections_list}

            for rd in self._row_widgets:
                conn_name = rd["conn_name"]
                if conn_name in active_conn_names:
                    saved_model_id = next(
                        (model_id for cn, model_id in active_connections_list if cn == conn_name),
                        None
                    )
                    rd["checkbox"].setChecked(True)
                    rd["combo"].setEnabled(True)

                    if saved_model_id:
                        idx = rd["combo"].findData(saved_model_id)
                        if idx != -1:
                            rd["combo"].setCurrentIndex(idx)

            # Восстановить active_connection_name и выделить строку
            active_conn_name = settings.current_settings.get("active_connection_name", "")
            if active_conn_name and active_conn_name != "Google Gemini":
                for rd in self._row_widgets:
                    if rd["conn_name"] == active_conn_name:
                        self._set_selection_highlight(rd["row_widget"])
                        break
            elif active_conn_name == "Google Gemini":
                self._gemini_selected = True
                self._gemini_radio.setChecked(True)

        self._block_signals = False

    def _on_gemini_radio_toggled(self, checked: bool):
        if self._block_signals:
            return
        if checked:
            self._gemini_selected = True
            self._clear_selection_highlight()
            # Uncheck all custom checkboxes
            for rd in self._row_widgets:
                rd["checkbox"].blockSignals(True)
                rd["checkbox"].setChecked(False)
                rd["checkbox"].blockSignals(False)
            model_id = self._gemini_model_combo.currentText() if self._gemini_model_combo else ""
            self.connections_changed.emit([])
            self.row_clicked.emit("Google Gemini", model_id)
            # Save to settings
            settings.current_settings["active_connection_name"] = "Google Gemini"
            # Clear active connections list when Gemini is selected
            settings.current_settings["active_connections_list"] = []
            settings.save_settings()
            if self.main_window:
                self.main_window.set_active_connection_name("Google Gemini")

    def _on_gemini_model_changed(self, text: str):
        if self._block_signals or not self._gemini_selected:
            return
        if "active_model_for_connection" not in settings.current_settings:
            settings.current_settings["active_model_for_connection"] = {}
        settings.current_settings["active_model_for_connection"]["Google Gemini"] = text
        self.model_changed.emit("Google Gemini", text)

    def _on_checkbox_toggled(self, row_data: dict, checked: bool):
        if self._block_signals:
            return
        if checked and self._gemini_radio:
            # Uncheck Gemini radio
            self._gemini_radio.blockSignals(True)
            self._gemini_radio.setChecked(False)
            self._gemini_radio.blockSignals(False)
            self._gemini_selected = False

        active = self.get_active_connections()
        self.connections_changed.emit(active)
        # Save active connections list to settings
        settings.current_settings["active_connections_list"] = active
        settings.save_settings()

        if checked:
            row_data["combo"].setEnabled(True)
            conn_name = row_data["conn_name"]
            model_id = row_data["combo"].currentData() or row_data["combo"].currentText()
            self.row_clicked.emit(conn_name, model_id)
            # Save as active connection
            settings.current_settings["active_connection_name"] = conn_name
            if self.main_window:
                self.main_window.set_active_connection_name(conn_name)
        elif not active:
            # Все подключения сняты — очистить active_connection_name
            settings.current_settings["active_connection_name"] = None
            settings.save_settings()
            if self.main_window:
                self.main_window.set_active_connection_name(None)

    def _on_model_combo_changed(self, row_data: dict, text: str):
        if self._block_signals:
            return
        conn_name = row_data["conn_name"]
        model_id = row_data["combo"].currentData() or text
        if "active_model_for_connection" not in settings.current_settings:
            settings.current_settings["active_model_for_connection"] = {}
        settings.current_settings["active_model_for_connection"][conn_name] = model_id
        self.model_changed.emit(conn_name, model_id)

    def _clear_selection_highlight(self):
        """Clear visual highlight from previously selected row."""
        if self._selected_row_widget:
            self._selected_row_widget.setProperty("connectionRowSelected", "false")
            self._selected_row_widget.style().unpolish(self._selected_row_widget)
            self._selected_row_widget.style().polish(self._selected_row_widget)
            self._selected_row_widget = None

    def _set_selection_highlight(self, row_widget: QtWidgets.QWidget):
        """Set visual highlight on selected row."""
        self._clear_selection_highlight()
        row_widget.setProperty("connectionRowSelected", "true")
        row_widget.style().unpolish(row_widget)
        row_widget.style().polish(row_widget)
        self._selected_row_widget = row_widget

    def _on_row_clicked(self, row_data: dict):
        conn_name = row_data["conn_name"]
        model_id = row_data["combo"].currentData() or row_data["combo"].currentText()
        self._set_selection_highlight(row_data["row_widget"])
        self.row_clicked.emit(conn_name, model_id)

    def _update_checkboxes_enabled(self, enabled: bool):
        for rd in self._row_widgets:
            rd["checkbox"].setEnabled(enabled)
            rd["combo"].setEnabled(enabled and rd["checkbox"].isChecked())

    def get_active_connections(self) -> list[tuple[str, str]]:
        """Return list of (conn_name, model_name) for checked custom connections."""
        result = []
        for rd in self._row_widgets:
            if rd["checkbox"].isChecked():
                conn_name = rd["conn_name"]
                model_id = rd["combo"].currentData() or rd["combo"].currentText()
                result.append((conn_name, model_id))
        return result

    def is_gemini_selected(self) -> bool:
        return self._gemini_selected

    def is_model_selected(self) -> bool:
        """Return True if a model is selected (Gemini or custom)."""
        if self._gemini_selected:
            # Gemini selected, check if model combo has a selection
            return bool(self._gemini_model_combo and self._gemini_model_combo.currentText())
        else:
            # Custom connections: check if any checkbox is checked
            return any(rd["checkbox"].isChecked() for rd in self._row_widgets)

    def _select_all_custom(self):
        self._block_signals = True
        if self._gemini_radio:
            self._gemini_radio.setChecked(False)
            self._gemini_selected = False
        for rd in self._row_widgets:
            rd["checkbox"].setChecked(True)
            rd["combo"].setEnabled(True)
        self._block_signals = False
        active = self.get_active_connections()
        self.connections_changed.emit(active)
        # Save active connections list to settings
        settings.current_settings["active_connections_list"] = active
        settings.save_settings()

    def _deselect_all_custom(self):
        self._block_signals = True
        for rd in self._row_widgets:
            rd["checkbox"].setChecked(False)
            rd["combo"].setEnabled(False)
        self._block_signals = False
        self._clear_selection_highlight()
        self.connections_changed.emit([])
        # Save active connections list to settings
        settings.current_settings["active_connections_list"] = []
        # Очистить active_connection_name
        settings.current_settings["active_connection_name"] = None
        settings.save_settings()
        if self.main_window:
            self.main_window.set_active_connection_name(None)


# ============================================================================
# Toast Notification Widget
# ============================================================================

class ToastNotification(QtWidgets.QFrame):
    """
    A toast-style notification popup that appears in the top-right corner.
    
    Features:
    - Slide-in animation from the right
    - Auto-hide for info/success types
    - Action button support
    - Close button
    """
    
    closed = QtCore.Signal(str)  # notification_id
    
    TOAST_SPACING = 8
    TOAST_MARGIN = 10
    ANIMATION_DURATION = 300
    TOAST_HEIGHT = 60
    TOAST_WIDTH = 400
    
    def __init__(self, notification: NotificationItem, manager: "NotificationManager", parent=None):
        super().__init__(parent)
        self.notification = notification
        self.manager = manager
        self._on_click: Optional[Callable] = None
        self._auto_hide_timer = QtCore.QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self._on_auto_hide)
        
        self._setup_ui()
        self._apply_style()
        self._setup_animation()
        
        # Set auto-hide if applicable
        style_config = NOTIFICATION_STYLES.get(notification.type, {})
        auto_hide_ms = style_config.get("auto_hide_ms")
        if auto_hide_ms:
            self._auto_hide_timer.start(auto_hide_ms)
    
    def _setup_ui(self):
        """Set up the UI elements."""
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setFrameShadow(QtWidgets.QFrame.Raised)
        self.setFixedHeight(self.TOAST_HEIGHT)
        self.setMinimumWidth(self.TOAST_WIDTH)
        self.setMaximumWidth(self.TOAST_WIDTH)
        
        # Main layout
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)
        
        # Icon
        style_config = NOTIFICATION_STYLES.get(self.notification.type, {})
        self.icon_label = QtWidgets.QLabel(style_config.get("icon", "ℹ️"))
        self.icon_label.setMinimumSize(24, 24)
        self.icon_label.setMaximumSize(24, 24)
        self.icon_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.icon_label)
        
        # Text - strip emoji icons from text since we show them separately
        text = self.notification.text
        self.text_label = QtWidgets.QLabel(text)
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label, stretch=1)
        
        layout.addStretch()
        
        if self.notification.button_text:
            self.action_button = QtWidgets.QPushButton(self.notification.button_text)
            self.action_button.setObjectName("action_button")
            self.action_button.setCursor(QtCore.Qt.PointingHandCursor)
            self.action_button.clicked.connect(self._on_action_clicked)
            layout.addWidget(self.action_button)
        
        self.close_button = QtWidgets.QPushButton("×")
        self.close_button.setObjectName("close_button")
        self.close_button.setMinimumSize(20, 20)
        self.close_button.setMaximumSize(20, 20)
        self.close_button.setCursor(QtCore.Qt.PointingHandCursor)
        self.close_button.clicked.connect(self._on_close_clicked)
        layout.addWidget(self.close_button)
    
    def _apply_style(self):
        self.setProperty("type", self.notification.type.value)
        self.style().unpolish(self)
        self.style().polish(self)
        
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        self.close_button.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
    
    def _setup_animation(self):
        parent_rect = self.parent().geometry() if self.parent() else QtCore.QRect(0, 0, 800, 600)
        start_x = parent_rect.width() + self.TOAST_SPACING
        self.move(start_x, self.y())
        
        self._anim = QtCore.QPropertyAnimation(self, b"pos")
        self._anim.setDuration(self.ANIMATION_DURATION)
        self._anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._anim.setStartValue(QtCore.QPoint(start_x, self.y()))
        self._anim.setEndValue(QtCore.QPoint(parent_rect.width() - self.width() - self.TOAST_MARGIN, self.y()))
        self._anim.start()
    
    def set_on_click(self, callback: Callable):
        self._on_click = callback
    
    def _on_action_clicked(self):
        if self._on_click:
            self._on_click()
        self._on_close_clicked()
    
    def _on_close_clicked(self):
        self._animate_out()
    
    def _on_auto_hide(self):
        self._animate_out()
    
    def _animate_out(self):
        self._auto_hide_timer.stop()

        if self.manager and hasattr(self.manager, '_cleanup_callback'):
            self.manager._cleanup_callback(self.notification.id)

        parent_rect = (
            self.parent().geometry() if self.parent() else QtCore.QRect(0, 0, 800, 600)
        )
        end_x = parent_rect.width() + self.TOAST_SPACING

        self._anim_out = QtCore.QPropertyAnimation(self, b"pos")
        self._anim_out.setDuration(self.ANIMATION_DURATION)
        self._anim_out.setEasingCurve(QtCore.QEasingCurve.InCubic)
        self._anim_out.setStartValue(self.pos())
        self._anim_out.setEndValue(QtCore.QPoint(end_x, self.y()))
        self._anim_out.finished.connect(self.deleteLater)
        self._anim_out.start(QtCore.QAbstractAnimation.DeleteWhenStopped)
        self.closed.emit(self.notification.id)



@auto_register(
    ("", "toolTip", "notification.bell.tooltip"),
)
class NotificationBell(QtWidgets.QPushButton):
    bell_clicked = QtCore.Signal()
    
    def __init__(self, manager: "NotificationManager", parent=None):
        super().__init__(parent)
        self.manager = manager
        self._notification_center: Optional["NotificationCenter"] = None
        self._unread_badge: Optional[QtWidgets.QLabel] = None
        self._click_count = 0
        self._click_timer = QtCore.QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._reset_click_count)
        self._test_type_index = 0
        self._test_types = [
            NotificationType.INFO,
            NotificationType.SUCCESS,
            NotificationType.WARNING,
            NotificationType.ERROR,
        ]
        
        self._setup_ui()
        self._connect_signals()
        self._update_display()
    
    def _setup_ui(self):
        self.setMinimumSize(36, 30)
        self.setMaximumSize(50, 30)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFlat(True)
        self.setText("🔔")
        self._unread_badge = QtWidgets.QLabel(self)
        self._unread_badge.setMinimumSize(16, 16)
        self._unread_badge.setMaximumSize(16, 16)
        self._unread_badge.setAlignment(QtCore.Qt.AlignCenter)
        self._unread_badge.setStyleSheet("""
            QLabel {
                background-color: #ff5555;
                color: white;
                border-radius: 8px;
                font-size: 10px;
                font-weight: bold;
            }
        """)
        self._unread_badge.hide()
        self._update_badge_position()
    
    def _update_badge_position(self):
        if self._unread_badge:
            x = self.width() - self._unread_badge.width() - 2
            y = 2
            self._unread_badge.move(x, y)
    
    def _connect_signals(self):
        self.clicked.connect(self._on_bell_clicked)
        self.manager.unread_count_changed.connect(self._on_unread_count_changed)
    
    def _on_bell_clicked(self):
        self._click_count += 1
        self._click_timer.start(500)
        
        if self._click_count >= 3:
            self._click_count = 0
            self._click_timer.stop()
            if settings.DEV_MODE_ENABLED:
                self._show_test_notification()
                return
        
        if self._notification_center is None:
            self._notification_center = NotificationCenter(self.manager, self.window())
        self._notification_center.show()
        self._notification_center.raise_()
        self._notification_center.activateWindow()
    
    def _reset_click_count(self):
        self._click_count = 0
    
    def _show_test_notification(self):
        notif_type = self._test_types[self._test_type_index]
        self._test_type_index = (self._test_type_index + 1) % len(self._test_types)
        
        type_names = {
            NotificationType.INFO: "Info",
            NotificationType.SUCCESS: "Success",
            NotificationType.WARNING: "Warning",
            NotificationType.ERROR: "Error",
        }
        
        type_name = type_names.get(notif_type, "Unknown")
        
        self.manager.show_notification(
            type=notif_type,
            text=f"[DEV TEST] {type_name} notification",
            button_text="Test Action",
            on_click=lambda: logger.debug(f"{type_name} action clicked"),
        )
    
    def _on_unread_count_changed(self, count: int):
        self._update_display()
    
    def _update_display(self):
        unread_count = self.manager.get_unread_count()
        
        if unread_count > 0:
            self._unread_badge.show()
            if unread_count > 99:
                self._unread_badge.setText("99+")
            else:
                self._unread_badge.setText(str(unread_count))
            self._unread_badge.adjustSize()
            self._update_badge_position()
        else:
            self._unread_badge.hide()
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_badge_position()

@auto_register(
    ("", "windowTitle", "notification.center.title"),
    ("filter_combo", "comboKeys", (
        "notification.center.filter_all",
        "notification.center.filter_info",
        "notification.center.filter_success",
        "notification.center.filter_warning",
        "notification.center.filter_error",
    )),
    ("clear_all_btn", "text", "notification.center.clear_all"),
    ("no_notifications_label", "text", "notification.center.no_notifications"),
)
class NotificationCenter(AnimatedDialog):
    
    def __init__(self, manager: "NotificationManager", parent=None):
        self.manager = manager
        super().__init__(parent)
        self.setMinimumSize(400, 450)
        self._setup_ui()
        self._connect_signals()
        self._populate_list()
        self._update_empty_state()
    
    def _setup_ui(self):
        load_ui("notification_center.ui", self, __file__)
        
        self.filter_combo.clear()
        self.filter_combo.addItem("All")
        self.filter_combo.addItem("Information")
        self.filter_combo.addItem("Success")
        self.filter_combo.addItem("Warnings")
        self.filter_combo.addItem("Errors")
        
        self.notifications_list.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: 1px solid #44475a;
                border-radius: 4px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #44475a;
            }
            QListWidget::item:selected {
                background-color: #44475a;
            }
            QListWidget::item:hover {
                background-color: #6272a4;
            }
        """)
    
    def _connect_signals(self):
        self.filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.clear_all_btn.clicked.connect(self._on_clear_all)
        self.manager.notification_added.connect(self._on_notification_added)
        self.manager.notification_removed.connect(self._on_notification_removed)
        self.manager.history_cleared.connect(self._on_history_cleared)
    
    def _populate_list(self):
        self.notifications_list.clear()
        
        filter_type = self._get_current_filter()
        notifications = self.manager.get_history()
        
        for notif in notifications:
            if filter_type and notif.type != filter_type:
                continue
            self._add_notification_item(notif)
        
        self._update_empty_state()
    
    def _get_current_filter(self) -> Optional[NotificationType]:
        index = self.filter_combo.currentIndex()
        if index == 0:
            return None
        types = [
            None,
            NotificationType.INFO,
            NotificationType.SUCCESS,
            NotificationType.WARNING,
            NotificationType.ERROR,
        ]
        return types[index] if index < len(types) else None
    
    def _add_notification_item(self, notif: NotificationItem):
        style_config = NOTIFICATION_STYLES.get(notif.type, {})
        icon = style_config.get("icon", "ℹ️")
        
        time_ago = self._format_time_ago(notif.timestamp)
        
        item_widget = QtWidgets.QWidget()
        item_widget.setObjectName("notification_item")
        item_layout = QtWidgets.QVBoxLayout(item_widget)
        item_layout.setContentsMargins(8, 6, 8, 6)
        item_layout.setSpacing(4)
        
        top_layout = QtWidgets.QHBoxLayout()
        top_layout.setSpacing(8)
        
        icon_label = QtWidgets.QLabel(icon)
        icon_label.setStyleSheet("font-size: 16px;")
        top_layout.addWidget(icon_label)
        
        text_label = QtWidgets.QLabel(notif.text)
        text_label.setWordWrap(True)
        text_label.setStyleSheet("color: #f8f8f2; font-size: 12px;")
        top_layout.addWidget(text_label, stretch=1)
        
        item_layout.addLayout(top_layout)
        
        bottom_layout = QtWidgets.QHBoxLayout()
        bottom_layout.setContentsMargins(24, 0, 0, 0)
        
        time_label = QtWidgets.QLabel(time_ago)
        time_label.setStyleSheet("color: #888; font-size: 11px;")
        bottom_layout.addWidget(time_label)
        
        bottom_layout.addStretch()
        
        delete_btn = QtWidgets.QPushButton()
        delete_btn.setObjectName("close_button")
        delete_btn.setCursor(QtCore.Qt.PointingHandCursor)
        delete_btn.clicked.connect(
            lambda _, nid=notif.id: self._on_delete_notification(nid)
        )
        bottom_layout.addWidget(delete_btn)
        
        item_layout.addLayout(bottom_layout)

        list_item = QtWidgets.QListWidgetItem(self.notifications_list)
        list_item.setSizeHint(item_widget.sizeHint())
        self.notifications_list.addItem(list_item)
        self.notifications_list.setItemWidget(list_item, item_widget)
    
    def _format_time_ago(self, timestamp: float) -> str:
        now = QtCore.QDateTime.currentSecsSinceEpoch()
        diff = now - timestamp
        
        if diff < 60:
            return translate("notification.center.time_now")
        elif diff < 3600:
            minutes = diff // 60
            return translate("notification.center.time_minutes", minutes=minutes)
        elif diff < 86400:
            hours = diff // 3600
            return translate("notification.center.time_hours", hours=hours)
        else:
            days = diff // 86400
            return translate("notification.center.time_days", days=days)
    
    def _update_empty_state(self):
        has_items = self.notifications_list.count() > 0
        self.no_notifications_label.setVisible(not has_items)
        self.notifications_list.setVisible(has_items)
    
    def _on_filter_changed(self, index: int):
        self._populate_list()
    
    def _on_clear_all(self):
        reply = QtWidgets.QMessageBox.question(
            self,
            translate("notification.center.clear_all_confirm_title"),
            translate("notification.center.clear_all_confirm_text"),
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self.manager.clear_history()
    
    def _on_delete_notification(self, notification_id: str):
        self.manager.remove_notification(notification_id)
        self._populate_list()
    
    def _on_notification_added(self, notification: NotificationItem):
        self._populate_list()
    
    def _on_notification_removed(self, notification_id: str):
        self._populate_list()
    
    def _on_history_cleared(self):
        self._populate_list()
    
    def showEvent(self, event):
        super().showEvent(event)
        self.manager.mark_all_as_read()
        self._populate_list()
