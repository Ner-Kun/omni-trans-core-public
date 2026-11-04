import json
import time
import random
import logging
import copy
from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtWidgets import QDialog
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    Dialog,
    FluentStyleSheet,
    LineEdit,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    SingleDirectionScrollArea,
    StrongBodyLabel,
    TableWidget,
    TextEdit,
)

from ..base_widgets import ShakeLineEdit
from ...localization_manager import loc_man, translate, auto_register
from ...utils import wip_notification
from ... import settings
from ...constants import (
    PROVIDER_API_BASES,
    PROVIDER_DISPLAY_NAMES,
    CLOUD_PROVIDERS,
    LOCAL_PROVIDERS,
    COMBINED_INFO_DIALOG_MIN_WIDTH,
    COMBINED_INFO_DIALOG_MIN_HEIGHT,
    PROVIDER_CONFIG_MAIN_SPACING,
    PROVIDER_GROUP_SPACING,
    PROVIDER_CONFIG_SPLITTER_SIZES,
    PROVIDER_MODELS_TABLE_MIN_HEIGHT,
    PROVIDER_TIMEOUT_MIN,
    PROVIDER_TIMEOUT_MAX,
    PROVIDER_DEFAULT_TIMEOUT,
    PROVIDER_LIMIT_VALIDATOR_MAX,
    PROVIDER_TPM_LIMIT_VALIDATOR_MAX,
    CONN_ID_RANDOM_RANGE_MIN,
    CONN_ID_RANDOM_RANGE_MAX,
    STATUS_INDICATOR_UNKNOWN_COLOR,
    STATUS_INDICATOR_FETCHING_COLOR,
    STATUS_INDICATOR_SUCCESS_COLOR,
    STATUS_INDICATOR_FAIL_COLOR,
    STATUS_INDICATOR_INACTIVE_COLOR,
)
from ...runnables import FetchModelsWorker, ModelInfoWorker
from .additional_params import AdditionalParametersDialog

logger = logging.getLogger('CORE_UI.dialogs')

PROVIDER_THINKING_MODE_KEYS = (
    "dialog.provider_config.thinking_mode.none",
    "dialog.provider_config.thinking_mode.auto",
    "dialog.provider_config.thinking_mode.by_commands",
    "dialog.provider_config.thinking_mode.by_header_body",
)
PROVIDER_MODEL_HEADER_KEYS = (
    "dialog.provider_config.header.model_id",
    "dialog.provider_config.header.limits",
)
# Mode values stored in the model config; order matches PROVIDER_THINKING_MODE_KEYS.
_THINKING_MODE_VALUES = ("none", "auto", "command", "header_body")


def _create_card(
    header_widget: QtWidgets.QWidget | None = None,
) -> tuple[CardWidget, QtWidgets.QVBoxLayout, StrongBodyLabel]:
    """Build a card with a bold title and return (card, body layout, title label)."""
    card = CardWidget()
    body_layout = QtWidgets.QVBoxLayout(card)
    body_layout.setContentsMargins(16, 12, 16, 12)
    body_layout.setSpacing(10)
    title_label = StrongBodyLabel(card)
    if header_widget is None:
        body_layout.addWidget(title_label)
    else:
        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(header_widget, 0, QtCore.Qt.AlignmentFlag.AlignRight)
        body_layout.addLayout(header_layout)
    return card, body_layout, title_label


@auto_register(
    ("connection_group_label", "text", "dialog.provider_config.group.connection_profile"),
    ("connection_name_label", "text", "dialog.provider_config.label.connection_name"),
    ("name_edit", "placeholderText", "dialog.provider_config.placeholder.connection_name"),
    ("provider_label", "text", "dialog.provider_config.label.provider"),
    ("base_url_label", "text", "dialog.provider_config.label.base_url"),
    ("api_key_label", "text", "dialog.provider_config.label.api_key"),
    ("timeout_label", "text", "dialog.provider_config.label.timeout"),
    ("global_limits_group_label", "text", "dialog.provider_config.group.global_limits"),
    ("global_rpm_label", "text", "dialog.provider_config.label.rpm"),
    ("global_rpd_label", "text", "dialog.provider_config.label.rpd"),
    ("global_tpm_label", "text", "dialog.provider_config.label.tpm"),
    ("wait_for_response_check", "text", "dialog.provider_config.check.sequential_processing"),
    ("wait_for_response_check", "toolTip", "dialog.provider_config.tooltip.sequential_processing"),
    ("models_group_label", "text", "dialog.provider_config.group.configured_models"),
    ("add_model_btn", "text", "dialog.provider_config.button.add_model"),
    ("remove_model_btn", "text", "dialog.provider_config.button.remove_model"),
    ("model_editor_widget_label", "text", "dialog.provider_config.group.model_settings"),
    ("model_id_editor_label", "text", "dialog.provider_config.label.model_id_editor"),
    ("available_models_label", "text", "dialog.provider_config.label.available_models"),
    ("info_button", "text", "dialog.provider_config.button.info"),
    ("status_indicator_label", "text", "dialog.provider_config.label.status_unknown"),
    ("fetch_models_btn", "text", "dialog.provider_config.button.get_models"),
    ("parsing_group_label", "text", "dialog.provider_config.group.parsing"),
    ("start_tag_edit", "placeholderText", "dialog.provider_config.placeholder.start_tag"),
    ("end_tag_edit", "placeholderText", "dialog.provider_config.placeholder.end_tag"),
    ("start_tag_label", "text", "dialog.provider_config.label.start_tag"),
    ("end_tag_label", "text", "dialog.provider_config.label.end_tag"),
    ("thinking_commands_group_label", "text", "dialog.provider_config.group.thinking_commands"),
    ("enable_cmd_label", "text", "dialog.provider_config.label.enable_cmd"),
    ("disable_cmd_label", "text", "dialog.provider_config.label.disable_cmd"),
    ("enable_cmd_edit", "placeholderText", "dialog.provider_config.placeholder.enable_cmd"),
    ("disable_cmd_edit", "placeholderText", "dialog.provider_config.placeholder.disable_cmd"),
    ("limits_group_label", "text", "dialog.provider_config.group.model_limits"),
    ("reset_model_settings_btn", "text", "dialog.provider_config.button.reset_model"),
    ("reset_model_settings_btn", "toolTip", "dialog.provider_config.button.reset_model_tooltip"),
    ("use_global_limits_check", "text", "dialog.provider_config.check.use_global_limits"),
    ("model_rpm_label", "text", "dialog.provider_config.label.rpm"),
    ("model_rpd_label", "text", "dialog.provider_config.label.rpd"),
    ("model_tpm_label", "text", "dialog.provider_config.label.tpm"),
    ("thinking_mode_group_label", "text", "dialog.provider_config.group.thinking_mode"),
    ("thinking_enabled_check", "text", "dialog.provider_config.check.enable_thinking"),
    ("thinking_mode_label", "text", "dialog.provider_config.label.thinking_mode"),
    ("configure_params_btn", "text", "dialog.provider_config.button.configure_params"),
    ("models_table", "horizontalHeaderKeys", PROVIDER_MODEL_HEADER_KEYS),
)
class ProviderConfigDialog(Dialog):
    _BASE_URL_READONLY_STYLE = "QLineEdit { color: #8a8a8a; }"

    def __init__(self, provider_to_edit=None, existing_config=None, parent=None):
        super().__init__("Connection", "", parent)
        self.setFixedSize(920, 660)
        self.contentLabel.hide()
        # В Dialog заголовок дублируется: windowTitleLabel сверху и titleLabel в теле.
        self.titleLabel.hide()
        self.windowTitleLabel.setContentsMargins(24, 12, 24, 0)
        self.yesButton.setText("Save")
        self.cancelButton.setText("Cancel")
        self.is_edit_mode = existing_config is not None
        self.existing_config = existing_config or {}
        self.provider_to_edit = provider_to_edit or self.existing_config.get("provider")
        self.configured_models = copy.deepcopy(
            self.existing_config.get("configured_models", [])
        )
        self.current_model_idx = -1
        self.fetched_models_cache = None
        self.placeholder_text = ""
        self.async_handler = ProviderConfigAsyncHandler(self)
        self.current_additional_params = {}
        self._build_ui()
        self._register_window_title()
        self._connect_signals()
        self._initial_setup()
        self._refresh_dynamic_localization()
        loc_man.language_changed.connect(self._refresh_dynamic_localization)

    def _build_ui(self):
        self._content = QtWidgets.QWidget(self)
        content_layout = QtWidgets.QVBoxLayout(self._content)
        content_layout.setContentsMargins(24, 8, 24, 12)
        content_layout.setSpacing(PROVIDER_CONFIG_MAIN_SPACING)

        self.connection_group, connection_layout, self.connection_group_label = (
            _create_card()
        )
        connection_grid = QtWidgets.QGridLayout()
        connection_grid.setContentsMargins(0, 0, 0, 0)
        connection_grid.setHorizontalSpacing(10)
        connection_grid.setVerticalSpacing(8)
        self.name_edit = LineEdit()
        self.provider_combo = ComboBox()
        self.base_url_edit = LineEdit()
        self.base_url_edit.installEventFilter(self)
        self.api_key_edit = LineEdit()
        self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.timeout_edit = ShakeLineEdit()
        self.timeout_edit.setValidator(
            QtGui.QIntValidator(PROVIDER_TIMEOUT_MIN, PROVIDER_TIMEOUT_MAX)
        )
        self.timeout_label = BodyLabel()
        self.connection_name_label = BodyLabel()
        self.provider_label = BodyLabel()
        self.base_url_label = BodyLabel()
        self.api_key_label = BodyLabel()
        connection_grid.addWidget(self.connection_name_label, 0, 0)
        connection_grid.addWidget(self.name_edit, 0, 1, 1, 3)
        connection_grid.addWidget(self.provider_label, 1, 0)
        connection_grid.addWidget(self.provider_combo, 1, 1, 1, 3)
        connection_grid.addWidget(self.base_url_label, 2, 0)
        connection_grid.addWidget(self.base_url_edit, 2, 1, 1, 3)
        connection_grid.addWidget(self.api_key_label, 3, 0)
        connection_grid.addWidget(self.api_key_edit, 3, 1)
        connection_grid.addWidget(self.timeout_label, 3, 2)
        connection_grid.addWidget(self.timeout_edit, 3, 3)
        connection_grid.setColumnStretch(1, 1)
        connection_grid.setColumnStretch(3, 1)
        connection_layout.addLayout(connection_grid)
        connection_layout.addStretch(1)

        self.global_limits_group, global_limits_layout, self.global_limits_group_label = (
            _create_card()
        )
        global_limits_grid = QtWidgets.QGridLayout()
        global_limits_grid.setContentsMargins(0, 0, 0, 0)
        global_limits_grid.setHorizontalSpacing(10)
        global_limits_grid.setVerticalSpacing(8)
        self.global_rpm_edit = ShakeLineEdit()
        self.global_rpd_edit = ShakeLineEdit()
        self.global_tpm_edit = ShakeLineEdit()
        int_validator_global = QtGui.QIntValidator(0, PROVIDER_LIMIT_VALIDATOR_MAX)
        self.global_rpm_edit.setValidator(int_validator_global)
        self.global_rpd_edit.setValidator(int_validator_global)
        self.global_tpm_edit.setValidator(
            QtGui.QIntValidator(0, PROVIDER_TPM_LIMIT_VALIDATOR_MAX)
        )
        self.global_rpm_label = BodyLabel()
        self.global_rpd_label = BodyLabel()
        self.global_tpm_label = BodyLabel()
        global_limits_grid.addWidget(self.global_rpm_label, 0, 0)
        global_limits_grid.addWidget(self.global_rpm_edit, 0, 1)
        global_limits_grid.addWidget(self.global_rpd_label, 1, 0)
        global_limits_grid.addWidget(self.global_rpd_edit, 1, 1)
        global_limits_grid.addWidget(self.global_tpm_label, 2, 0)
        global_limits_grid.addWidget(self.global_tpm_edit, 2, 1)
        global_limits_grid.setColumnStretch(1, 1)
        self.wait_for_response_check = CheckBox()
        global_limits_layout.addLayout(global_limits_grid)
        global_limits_layout.addWidget(self.wait_for_response_check)
        global_limits_layout.addStretch(1)

        content_layout.addWidget(self.connection_group)

        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)

        models_column = QtWidgets.QWidget()
        models_column_layout = QtWidgets.QVBoxLayout(models_column)
        models_column_layout.setContentsMargins(0, 0, 0, 0)
        models_column_layout.setSpacing(PROVIDER_CONFIG_MAIN_SPACING)

        self.models_group, models_group_layout, self.models_group_label = _create_card()
        self.models_table = TableWidget()
        self.models_table.setColumnCount(2)
        self.models_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.models_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.models_table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        self.models_table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self.models_table.verticalHeader().setVisible(False)
        self.models_table.setMinimumHeight(PROVIDER_MODELS_TABLE_MIN_HEIGHT)
        models_group_layout.addWidget(self.models_table, 1)
        models_buttons_layout = QtWidgets.QHBoxLayout()
        models_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.add_model_btn = PrimaryPushButton()
        self.remove_model_btn = PushButton()
        models_buttons_layout.addStretch()
        models_buttons_layout.addWidget(self.add_model_btn)
        models_buttons_layout.addWidget(self.remove_model_btn)
        models_group_layout.addLayout(models_buttons_layout)
        models_column_layout.addWidget(self.models_group, 1)
        models_column_layout.addWidget(self.global_limits_group)
        self.main_splitter.addWidget(models_column)

        self.model_editor_widget, editor_layout, self.model_editor_widget_label = (
            _create_card()
        )
        form_layout = QtWidgets.QFormLayout()
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setVerticalSpacing(8)
        self.model_id_edit = LineEdit()
        self.model_id_editor_label = BodyLabel()
        form_layout.addRow(self.model_id_editor_label, self.model_id_edit)
        self.available_models_combo = ComboBox()
        # Длинные id моделей не должны раздувать минимальную ширину диалога.
        self.available_models_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.available_models_label = BodyLabel()
        form_layout.addRow(self.available_models_label, self.available_models_combo)
        actions_layout = QtWidgets.QHBoxLayout()
        actions_layout.setContentsMargins(0, 0, 0, 0)
        self.info_button = PushButton()
        status_layout = QtWidgets.QHBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)
        self.status_indicator_icon = BodyLabel("●")
        self.status_indicator_label = CaptionLabel()
        self.status_indicator_label.setStyleSheet(
            f"color: {STATUS_INDICATOR_UNKNOWN_COLOR};"
        )
        status_layout.addStretch()
        status_layout.addWidget(
            self.status_indicator_icon,
            alignment=QtCore.Qt.AlignmentFlag.AlignRight,
        )
        status_layout.addWidget(
            self.status_indicator_label,
            alignment=QtCore.Qt.AlignmentFlag.AlignLeft,
        )
        status_layout.addStretch()
        self.fetch_models_btn = PrimaryPushButton()
        actions_layout.addWidget(self.info_button, 1)
        actions_layout.addLayout(status_layout, 0)
        actions_layout.addWidget(self.fetch_models_btn, 1)
        form_layout.addRow(actions_layout)
        editor_layout.addLayout(form_layout)

        self.parsing_group, parsing_layout, self.parsing_group_label = _create_card()
        tags_layout = QtWidgets.QHBoxLayout()
        tags_layout.setContentsMargins(0, 0, 0, 0)
        self.start_tag_edit = LineEdit()
        self.end_tag_edit = LineEdit()
        self.start_tag_label = BodyLabel()
        self.end_tag_label = BodyLabel()
        tags_layout.addWidget(self.start_tag_label)
        tags_layout.addWidget(self.start_tag_edit, 1)
        tags_layout.addSpacing(PROVIDER_GROUP_SPACING)
        tags_layout.addWidget(self.end_tag_label)
        tags_layout.addWidget(self.end_tag_edit, 1)
        parsing_layout.addLayout(tags_layout)
        parsing_layout.addStretch(1)
        editor_layout.addWidget(self.parsing_group)

        self.thinking_mode_group, thinking_mode_layout, self.thinking_mode_group_label = (
            _create_card()
        )
        # Чекбокс включения/выключения мышления для этой модели
        self.thinking_enabled_check = CheckBox()
        thinking_mode_layout.addWidget(self.thinking_enabled_check)
        self.thinking_mode_combo = ComboBox()
        self.thinking_mode_label = BodyLabel()
        self.configure_params_btn = PushButton()
        self.configure_params_btn.setVisible(False)
        thinking_mode_combo_layout = QtWidgets.QHBoxLayout()
        thinking_mode_combo_layout.setContentsMargins(0, 0, 0, 0)
        thinking_mode_combo_layout.addWidget(self.thinking_mode_label)
        thinking_mode_combo_layout.addWidget(self.thinking_mode_combo, 1)
        thinking_mode_combo_layout.addWidget(self.configure_params_btn)
        thinking_mode_layout.addLayout(thinking_mode_combo_layout)
        thinking_mode_layout.addStretch(1)
        editor_layout.addWidget(self.thinking_mode_group)

        self.thinking_commands_group, thinking_commands_layout, self.thinking_commands_group_label = (
            _create_card()
        )
        commands_row = QtWidgets.QHBoxLayout()
        commands_row.setContentsMargins(0, 0, 0, 0)
        self.enable_cmd_edit = LineEdit()
        self.disable_cmd_edit = LineEdit()
        self.enable_cmd_label = BodyLabel()
        self.disable_cmd_label = BodyLabel()
        commands_row.addWidget(self.enable_cmd_label)
        commands_row.addWidget(self.enable_cmd_edit, 1)
        thinking_commands_layout.addLayout(commands_row)
        disable_cmd_row = QtWidgets.QHBoxLayout()
        disable_cmd_row.setContentsMargins(0, 0, 0, 0)
        disable_cmd_row.addWidget(self.disable_cmd_label)
        disable_cmd_row.addWidget(self.disable_cmd_edit, 1)
        thinking_commands_layout.addLayout(disable_cmd_row)
        self.thinking_commands_group.setVisible(False)
        editor_layout.addWidget(self.thinking_commands_group)

        self.reset_model_settings_btn = PushButton()
        self.limits_group, limits_layout, self.limits_group_label = _create_card(
            self.reset_model_settings_btn
        )
        self.use_global_limits_check = CheckBox()
        limits_layout.addWidget(self.use_global_limits_check)
        limits_grid_layout = QtWidgets.QGridLayout()
        limits_grid_layout.setContentsMargins(0, 0, 0, 0)
        limits_grid_layout.setHorizontalSpacing(10)
        limits_grid_layout.setVerticalSpacing(8)
        self.rpm_edit = ShakeLineEdit()
        self.rpd_edit = ShakeLineEdit()
        self.tpm_edit = ShakeLineEdit()
        int_validator = QtGui.QIntValidator(0, PROVIDER_LIMIT_VALIDATOR_MAX)
        self.rpm_edit.setValidator(int_validator)
        self.rpd_edit.setValidator(int_validator)
        self.tpm_edit.setValidator(
            QtGui.QIntValidator(0, PROVIDER_TPM_LIMIT_VALIDATOR_MAX)
        )
        self.model_rpm_label = BodyLabel()
        self.model_rpd_label = BodyLabel()
        self.model_tpm_label = BodyLabel()
        limits_grid_layout.addWidget(self.model_rpm_label, 0, 0)
        limits_grid_layout.addWidget(self.rpm_edit, 0, 1)
        limits_grid_layout.addWidget(self.model_rpd_label, 0, 2)
        limits_grid_layout.addWidget(self.rpd_edit, 0, 3)
        limits_grid_layout.addWidget(self.model_tpm_label, 1, 0)
        limits_grid_layout.addWidget(self.tpm_edit, 1, 1, 1, 3)
        limits_grid_layout.setColumnStretch(1, 1)
        limits_grid_layout.setColumnStretch(3, 1)
        limits_layout.addLayout(limits_grid_layout)
        limits_layout.addStretch(1)
        editor_layout.addWidget(self.limits_group)
        editor_layout.addStretch(1)

        self.main_splitter.addWidget(self.model_editor_widget)
        self.main_splitter.setSizes(PROVIDER_CONFIG_SPLITTER_SIZES)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)

        content_layout.addWidget(self.main_splitter, 1)
        self.info_label = CaptionLabel()
        self.info_label.setStyleSheet(
            f"color: {STATUS_INDICATOR_UNKNOWN_COLOR};"
        )
        self.info_label.setWordWrap(True)
        content_layout.addWidget(self.info_label)

        # Контент выше фиксированной высоты диалога, поэтому прокручивается целиком.
        self.content_scroll = SingleDirectionScrollArea(
            orient=QtCore.Qt.Orientation.Vertical
        )
        self.content_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.content_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        self.content_scroll.viewport().setAutoFillBackground(False)
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.content_scroll.setWidget(self._content)

        self.textLayout.setContentsMargins(0, 0, 0, 0)
        self.textLayout.setSpacing(0)
        self.vBoxLayout.insertWidget(1, self.content_scroll, 1)
        # Скрытые заголовок и contentLabel не должны забирать высоту у контента.
        self.vBoxLayout.setStretchFactor(self.textLayout, 0)
        self.ok_button = self.yesButton

    def accept(self):
        if not self._validate_form():
            return
        super().accept()

    def _alert(self, title: str, text: str) -> None:
        box = MessageBox(title, text, self)
        box.hideCancelButton()
        box.exec()

    def _confirm(self, title: str, text: str) -> bool:
        box = MessageBox(title, text, self)
        return box.exec() == QDialog.DialogCode.Accepted

    def eventFilter(self, watched, event):
        if watched is self.base_url_edit and event.type() == QtCore.QEvent.Type.MouseButtonDblClick:
            if self.base_url_edit.isReadOnly():
                self.base_url_edit.setReadOnly(False)
                FluentStyleSheet.LINE_EDIT.apply(self.base_url_edit)
                return True
        return super().eventFilter(watched, event)

    def _update_base_url_state(self):
        provider_id = self.provider_combo.currentData()
        is_cloud_provider = provider_id in CLOUD_PROVIDERS
        is_readonly = is_cloud_provider and provider_id != "openai_compatible"
        self.base_url_edit.setReadOnly(is_readonly)
        if is_readonly:
            self.base_url_edit.setStyleSheet(self._BASE_URL_READONLY_STYLE)
            loc_man.register(
                self.base_url_edit,
                "toolTip",
                "dialog.provider_config.tooltip.base_url_cloud",
            )
        else:
            FluentStyleSheet.LINE_EDIT.apply(self.base_url_edit)
            self.base_url_edit.setToolTip("")

    def _register_window_title(self):
        conn_name = self.existing_config.get('name', '')
        if self.is_edit_mode:
            loc_man.register(self, "windowTitle", "dialog.provider_config.edit_title", conn_name=conn_name)
        else:
            loc_man.register(self, "windowTitle", "dialog.provider_config.add_title")

    def retranslate(self):
        """Rebuild option texts (combo boxes hold no localizable widgets of their own)."""
        current_mode = self.thinking_mode_combo.currentData()
        self.thinking_mode_combo.blockSignals(True)
        for index, key in enumerate(PROVIDER_THINKING_MODE_KEYS):
            self.thinking_mode_combo.setItemText(index, translate(key))
        if current_mode is not None:
            mode_index = self.thinking_mode_combo.findData(current_mode)
            if mode_index != -1:
                self.thinking_mode_combo.setCurrentIndex(mode_index)
        self.thinking_mode_combo.blockSignals(False)

    def _refresh_dynamic_localization(self):
        self.placeholder_text = translate("dialog.provider_config.placeholder.provider")
        current_provider_text = self.provider_combo.currentText()
        if (
            self.provider_combo.count() > 0
            and self.provider_combo.itemText(0) != self.placeholder_text
        ):
            self.provider_combo.setItemText(0, self.placeholder_text)
        self.retranslate()
        self._populate_models_table()
        self._on_provider_changed(current_provider_text, from_retranslate=True)

    def _connect_signals(self):
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        self.name_edit.textChanged.connect(self._validate_form)
        self.api_key_edit.textChanged.connect(self._validate_form)
        self.models_table.itemSelectionChanged.connect(self._on_model_selection_changed)
        self.add_model_btn.clicked.connect(self._add_new_model)
        self.remove_model_btn.clicked.connect(self._remove_selected_model)
        self.fetch_models_btn.clicked.connect(self.async_handler.fetch_models_and_info)
        self.available_models_combo.currentTextChanged.connect(
            self._on_available_model_selected
        )
        self.reset_model_settings_btn.clicked.connect(
            self._reset_current_model_settings
        )
        self.info_button.clicked.connect(self.async_handler.show_combined_model_info)
        self.thinking_mode_combo.currentIndexChanged.connect(
            self._on_thinking_mode_changed
        )
        self.thinking_mode_combo.currentIndexChanged.connect(
            self._save_current_model_data
        )
        self.configure_params_btn.clicked.connect(self._open_additional_params_dialog)
        self.model_id_edit.textChanged.connect(self._on_model_id_edited)
        self.model_id_edit.editingFinished.connect(self._commit_model_id_from_editor)
        self.start_tag_edit.editingFinished.connect(self._save_current_model_data)
        self.end_tag_edit.editingFinished.connect(self._save_current_model_data)
        self.enable_cmd_edit.editingFinished.connect(self._save_current_model_data)
        self.disable_cmd_edit.editingFinished.connect(self._save_current_model_data)
        self.use_global_limits_check.toggled.connect(self._save_current_model_data)
        self.rpm_edit.editingFinished.connect(self._save_current_model_data)
        self.rpd_edit.editingFinished.connect(self._save_current_model_data)
        self.tpm_edit.editingFinished.connect(self._save_current_model_data)
        self.timeout_edit.textChanged.connect(self._validate_form)

    def _on_thinking_mode_changed(self, index: int):
        mode = self.thinking_mode_combo.itemData(index)
        self.thinking_commands_group.setVisible(mode == "command")
        self.configure_params_btn.setVisible(mode == "header_body")

    def _open_additional_params_dialog(self):
        if not (0 <= self.current_model_idx < len(self.configured_models)):
            return

        dialog = AdditionalParametersDialog(self.current_additional_params, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.current_additional_params = dialog.get_data()
            self._save_current_model_data()

    def _update_thinking_controls_visibility(self, mode_text=""):
        if not mode_text:
            mode_text = self.thinking_mode_combo.currentText()
        is_command_mode = translate("dialog.provider_config.mode.command") in mode_text
        self.thinking_commands_group.setVisible(is_command_mode)

    def _save_current_model_data(self):
        if not (0 <= self.current_model_idx < len(self.configured_models)):
            return

        def get_int_or_none(widget: QtWidgets.QLineEdit):
            text = widget.text().strip()
            return int(text) if text.isdigit() else None

        current_model = self.configured_models[self.current_model_idx]
        current_model["parsing_rules"] = {
            "start_tag": self.start_tag_edit.text().strip(),
            "end_tag": self.end_tag_edit.text().strip(),
        }

        thinking_config = current_model.get("thinking_config", {})
        thinking_config["enabled"] = self.thinking_enabled_check.isChecked()
        thinking_config["mode"] = self.thinking_mode_combo.currentData()
        thinking_config["enable_cmd"] = self.enable_cmd_edit.text().strip()
        thinking_config["disable_cmd"] = self.disable_cmd_edit.text().strip()
        current_model["thinking_config"] = thinking_config

        current_model["additional_params"] = self.current_additional_params
        logger.debug(
            f"Saving additional_params into model config '{current_model.get('model_id')}': {self.current_additional_params}"
        )
        use_global_limits = self.use_global_limits_check.isChecked()
        current_model["limits"] = {
            "use_global_limits": use_global_limits,
            "rpm": get_int_or_none(self.rpm_edit),
            "rpd": get_int_or_none(self.rpd_edit),
            "tpm": get_int_or_none(self.tpm_edit),
        }
        self.rpm_edit.setEnabled(not use_global_limits)
        self.rpd_edit.setEnabled(not use_global_limits)
        self.tpm_edit.setEnabled(not use_global_limits)
        full_model_id = current_model.get("model_id", "")
        clean_model_id = (
            full_model_id.split("/")[-1] if "/" in full_model_id else full_model_id
        )
        self.models_table.item(self.current_model_idx, 0).setText(clean_model_id)
        limits_status = (
            translate("dialog.provider_config.limits_status_global")
            if use_global_limits
            else translate("dialog.provider_config.limits_status_custom")
        )
        self.models_table.item(self.current_model_idx, 1).setText(limits_status)
        self._validate_form()

    def _add_new_model(self):
        new_model = {
            "model_id": f"new-model-{len(self.configured_models) + 1}",
            "parsing_rules": {"start_tag": "", "end_tag": ""},
            "limits": {
                "use_global_limits": True,
                "rpm": None,
                "rpd": None,
                "tpm": None,
            },
            "thinking_config": {"mode": "none", "enabled": True, "enable_cmd": "", "disable_cmd": ""},
            "additional_params": {
                "include_body_params": "",
                "exclude_body_params": "",
                "include_headers": "",
            },
        }
        self.configured_models.append(new_model)
        self._populate_models_table()
        self._validate_form()
        self.models_table.selectRow(self.models_table.rowCount() - 1)
        self.model_id_edit.selectAll()
        self.model_id_edit.setFocus()

    def _remove_selected_model(self):
        if self.current_model_idx == -1:
            return
        model_id_to_remove = self.configured_models[self.current_model_idx].get(
            "model_id", "N/A"
        )
        title = translate("dialog.provider_config.prompt.remove_model_title")
        text = translate(
            "dialog.provider_config.prompt.remove_model_text",
            model_id_to_remove=model_id_to_remove,
        )
        if self._confirm(title, text):
            del self.configured_models[self.current_model_idx]
            self.current_model_idx = -1
            self._populate_models_table()
            self._validate_form()
            if self.models_table.rowCount() > 0:
                self.models_table.selectRow(0)
            else:
                self._clear_editor_fields()
                self.model_editor_widget.setEnabled(False)

    def _reset_current_model_settings(self):
        if not (0 <= self.current_model_idx < len(self.configured_models)):
            return
        model_config = self.configured_models[self.current_model_idx]
        model_id = model_config.get("model_id", "N/A")
        title = translate("dialog.provider_config.prompt.reset_model_title")
        text = translate(
            "dialog.provider_config.prompt.reset_model_text", model_id=model_id
        )
        if self._confirm(title, text):
            logger.debug(f"Resetting settings for model '{model_id}'.")
            model_config["limits"] = {
                "use_global_limits": True,
                "rpm": None,
                "rpd": None,
                "tpm": None,
            }
            model_config["parsing_rules"] = {"start_tag": "", "end_tag": ""}
            model_config["thinking_config"] = {
                "mode": "none",
                "enabled": True,
                "enable_cmd": "",
                "disable_cmd": "",
            }
            model_config["additional_params"] = {
                "include_body_params": "",
                "exclude_body_params": "",
                "include_headers": "",
            }
            self._load_model_data_into_editor(model_config)
            self._save_current_model_data()

    def _initial_setup(self):
        self.thinking_mode_combo.blockSignals(True)
        for key, mode in zip(PROVIDER_THINKING_MODE_KEYS, _THINKING_MODE_VALUES):
            self.thinking_mode_combo.addItem(translate(key), userData=mode)
        self.thinking_mode_combo.blockSignals(False)

        self._set_status_indicator(
            STATUS_INDICATOR_INACTIVE_COLOR,
            translate("dialog.provider_config.label.status_unknown"),
        )
        self.provider_combo.blockSignals(True)
        self.provider_combo.addItem(self.placeholder_text, userData="")

        def add_providers_to_combo(provider_list):
            for provider_id in sorted(
                provider_list, key=lambda p: PROVIDER_DISPLAY_NAMES.get(p, p)
            ):
                display_name = PROVIDER_DISPLAY_NAMES.get(
                    provider_id, provider_id
                )
                self.provider_combo.addItem(display_name, userData=provider_id)

        add_providers_to_combo(CLOUD_PROVIDERS)
        self.provider_combo.addItem("──────────────")
        self.provider_combo.setItemEnabled(self.provider_combo.count() - 1, False)
        add_providers_to_combo(LOCAL_PROVIDERS)
        self.provider_combo.blockSignals(False)
        self.timeout_edit.setText(str(PROVIDER_DEFAULT_TIMEOUT))
        self.wait_for_response_check.setChecked(True)
        if self.is_edit_mode:
            self.name_edit.setText(self.existing_config.get("name", ""))
            provider_id_to_find = self.provider_to_edit
            index = self.provider_combo.findData(provider_id_to_find)
            if index != -1:
                self.provider_combo.setCurrentIndex(index)
            else:
                self.provider_combo.setCurrentText(provider_id_to_find)
            self.base_url_edit.setText(self.existing_config.get("base_url", ""))
            self.timeout_edit.setText(
                str(self.existing_config.get("timeout", PROVIDER_DEFAULT_TIMEOUT))
            )
            self.api_key_edit.setText(self.existing_config.get("api_key", ""))
            self.wait_for_response_check.setChecked(
                self.existing_config.get("wait_for_response", True)
            )
            global_limits = self.existing_config.get("global_limits", {})
            rpm_val = global_limits.get("rpm")
            self.global_rpm_edit.setText(str(rpm_val) if rpm_val is not None else "")
            rpd_val = global_limits.get("rpd")
            self.global_rpd_edit.setText(str(rpd_val) if rpd_val is not None else "")
            tpm_val = global_limits.get("tpm")
            self.global_tpm_edit.setText(str(tpm_val) if tpm_val is not None else "")
        else:
            self._on_provider_changed(self.provider_combo.currentText())
        self._populate_models_table()
        self._update_base_url_state()
        self._validate_form()
        if self.models_table.rowCount() > 0:
            self.models_table.selectRow(0)
        else:
            self.model_editor_widget.setEnabled(False)

    @QtCore.Slot(str)
    def _on_provider_changed(self, provider_name, from_retranslate=False):
        provider_id = self.provider_combo.currentData()
        if (
            self.is_edit_mode
            and provider_id != self.provider_to_edit
            and not from_retranslate
        ):
            title = translate(
                "dialog.provider_config.prompt.confirm_provider_change_title"
            )
            text = translate(
                "dialog.provider_config.prompt.confirm_provider_change_text"
            )
            if not self._confirm(title, text):
                self.provider_combo.blockSignals(True)
                index = self.provider_combo.findData(self.provider_to_edit)
                if index != -1:
                    self.provider_combo.setCurrentIndex(index)
                self.provider_combo.blockSignals(False)
                return
            else:
                self.configured_models.clear()
                self.provider_to_edit = provider_id

        is_provider_selected = bool(provider_id)
        self.base_url_edit.setEnabled(is_provider_selected)
        self.api_key_edit.setEnabled(is_provider_selected)
        self.fetch_models_btn.setEnabled(is_provider_selected)
        if is_provider_selected:
            if not from_retranslate:
                self.base_url_edit.setText(PROVIDER_API_BASES.get(provider_id, ""))
            self.info_label.setText(
                translate(
                    "dialog.provider_config.info_label.provider_selected",
                    provider_name=provider_name,
                )
            )
        else:
            if not from_retranslate:
                self.base_url_edit.clear()
            self.info_label.setText(
                translate("dialog.provider_config.info_label.begin")
            )

        self.fetched_models_cache = None
        self._populate_models_table()
        self._set_status_indicator(
            "⚪️", translate("dialog.provider_config.label.status_unknown")
        )
        self._update_base_url_state()
        self._validate_form()

    def _populate_models_table(self):
        self.models_table.blockSignals(True)
        self.models_table.setRowCount(0)
        self.models_table.setRowCount(len(self.configured_models))
        for i, model_data in enumerate(self.configured_models):
            full_model_id = model_data.get("model_id", "N/A")
            clean_model_id = (
                full_model_id.split("/")[-1] if "/" in full_model_id else full_model_id
            )
            model_id_item = QtWidgets.QTableWidgetItem(clean_model_id)
            limits = model_data.get("limits", {})
            use_global = limits.get("use_global_limits", True)
            limits_status = (
                translate("dialog.provider_config.limits_status_global")
                if use_global
                else translate("dialog.provider_config.limits_status_custom")
            )
            limits_item = QtWidgets.QTableWidgetItem(limits_status)
            limits_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            tooltip_text = f"{translate('dialog.provider_config.limits_status_global')}: {translate('dialog.provider_config.tooltip.limits_profile')}\n{translate('dialog.provider_config.limits_status_custom')}: {translate('dialog.provider_config.tooltip.limits_custom')}"
            limits_item.setToolTip(tooltip_text)
            self.models_table.setItem(i, 0, model_id_item)
            self.models_table.setItem(i, 1, limits_item)
        self.models_table.blockSignals(False)
        self.remove_model_btn.setEnabled(self.models_table.rowCount() > 0)
        if self.models_table.rowCount() == 0:
            self._clear_editor_fields()
            self.model_editor_widget.setEnabled(False)

    @QtCore.Slot(str)
    def _on_available_model_selected(self, model_display_name):
        if not self.model_editor_widget.isEnabled() or not model_display_name:
            return
        full_model_id = self.available_models_combo.currentData()
        if not full_model_id:
            return
        if 0 <= self.current_model_idx < len(self.configured_models):
            self.configured_models[self.current_model_idx]["model_id"] = full_model_id
            self.model_id_edit.setText(model_display_name)
            self._save_current_model_data()

    def _on_model_selection_changed(self):
        selected_items = self.models_table.selectedItems()
        is_selection_present = bool(selected_items)
        self.model_editor_widget.setEnabled(is_selection_present)
        if is_selection_present:
            self.current_model_idx = self.models_table.row(selected_items[0])
            if 0 <= self.current_model_idx < len(self.configured_models):
                model_data = self.configured_models[self.current_model_idx]
                self._load_model_data_into_editor(model_data)
        else:
            self.current_model_idx = -1
            self._clear_editor_fields()

    def _load_model_data_into_editor(self, model_data):
        logger.debug(f"Loading data into editor. Full model_data: {model_data}")
        full_model_id = model_data.get("model_id", "")
        clean_model_id = (
            full_model_id.split("/")[-1] if "/" in full_model_id else full_model_id
        )
        self.model_id_edit.setText(clean_model_id)
        parsing_rules = model_data.get("parsing_rules", {})
        self.start_tag_edit.setText(parsing_rules.get("start_tag", ""))
        self.end_tag_edit.setText(parsing_rules.get("end_tag", ""))

        # Загрузка состояния чекбокса включения/выключения мышления
        thinking_config = model_data.get("thinking_config", {})
        thinking_enabled = thinking_config.get("enabled", True)
        self.thinking_enabled_check.setChecked(thinking_enabled)

        self.thinking_mode_combo.blockSignals(True)
        mode = thinking_config.get("mode", "none")
        if self.thinking_mode_combo.findData(mode) == -1:
            logger.warning(
                f"Found unknown thinking mode '{mode}' in settings. Defaulting to 'none'."
            )
            mode = "none"
        index = self.thinking_mode_combo.findData(mode)
        self.thinking_mode_combo.setCurrentIndex(index)
        self.thinking_mode_combo.blockSignals(False)

        self._on_thinking_mode_changed(index)

        self.enable_cmd_edit.setText(thinking_config.get("enable_cmd", ""))
        self.disable_cmd_edit.setText(thinking_config.get("disable_cmd", ""))

        default_additional_params = {
            "include_body_params": "",
            "exclude_body_params": "",
            "include_headers": "",
        }
        loaded_params = model_data.get("additional_params") or {}
        default_additional_params.update(loaded_params)
        self.current_additional_params = default_additional_params

        limits = model_data.get("limits", {})
        use_global = limits.get("use_global_limits", True)
        self.use_global_limits_check.setChecked(use_global)
        rpm_val = limits.get("rpm")
        self.rpm_edit.setText(str(rpm_val) if rpm_val is not None else "")
        rpd_val = limits.get("rpd")
        self.rpd_edit.setText(str(rpd_val) if rpd_val is not None else "")
        tpm_val = limits.get("tpm")
        self.tpm_edit.setText(str(tpm_val) if tpm_val is not None else "")
        is_custom_limits = not use_global
        self.rpm_edit.setEnabled(is_custom_limits)
        self.rpd_edit.setEnabled(is_custom_limits)
        self.tpm_edit.setEnabled(is_custom_limits)

    def _clear_editor_fields(self):
        self.model_id_edit.clear()
        self.available_models_combo.clear()
        self.start_tag_edit.clear()
        self.end_tag_edit.clear()
        self.enable_cmd_edit.clear()
        self.disable_cmd_edit.clear()
        self.use_global_limits_check.setChecked(True)
        self.rpm_edit.clear()
        self.rpd_edit.clear()
        self.tpm_edit.clear()

    @QtCore.Slot(str)
    def _on_model_id_edited(self, model_name):
        self.available_models_combo.blockSignals(True)
        index = self.available_models_combo.findText(model_name)
        if index != -1:
            self.available_models_combo.setCurrentIndex(index)
        else:
            self.available_models_combo.setCurrentIndex(-1)
        self.available_models_combo.blockSignals(False)

    def _commit_model_id_from_editor(self):
        if not (0 <= self.current_model_idx < len(self.configured_models)):
            return
        entered_text = self.model_id_edit.text().strip()
        if not entered_text:
            return
        index = self.available_models_combo.findText(entered_text)
        if index != -1:
            full_model_id = self.available_models_combo.itemData(index)
            self.configured_models[self.current_model_idx]["model_id"] = full_model_id
        else:
            self.configured_models[self.current_model_idx]["model_id"] = entered_text
        self._save_current_model_data()

    def _validate_form(self) -> bool:
        is_valid = bool(
            self.name_edit.text().strip() and
            self.provider_combo.currentText() != self.placeholder_text and
            self.api_key_edit.text().strip() and
            self.configured_models)
        self.ok_button.setEnabled(is_valid)
        return is_valid

    def _set_status_indicator(self, emoji, tooltip):
        self.status_indicator_icon.setText(emoji)
        self.status_indicator_label.setText(tooltip)

    def _resolve_api_keys(self) -> list[str]:
        edited_key = self.api_key_edit.text().strip()
        existing = self.existing_config.get("api_keys") or []
        if not existing:
            return [edited_key] if edited_key else []
        existing_first = str(existing[0]).strip()
        if edited_key and edited_key != existing_first:
            return [edited_key]
        return [str(key) for key in existing if str(key).strip()]

    def get_data(self):
        provider_id = self.provider_combo.currentData()
        if not provider_id:
            return None

        def get_int_or_none(widget: QtWidgets.QLineEdit):
            text = widget.text().strip()
            return int(text) if text.isdigit() else None

        connection_data = {
            "id": self.existing_config.get(
                "id",
                f"conn_{int(time.time())}_{random.randint(CONN_ID_RANDOM_RANGE_MIN, CONN_ID_RANDOM_RANGE_MAX)}",
            ),
            "name": self.name_edit.text().strip(),
            "provider": provider_id,
            "api_key": self.api_key_edit.text().strip(),
            "api_keys": self._resolve_api_keys(),
            "base_url": self.base_url_edit.text().strip(),
            "timeout": get_int_or_none(self.timeout_edit) or PROVIDER_DEFAULT_TIMEOUT,
            "wait_for_response": self.wait_for_response_check.isChecked(),
            "global_limits": {
                "rpm": get_int_or_none(self.global_rpm_edit),
                "rpd": get_int_or_none(self.global_rpd_edit),
                "tpm": get_int_or_none(self.global_tpm_edit),
            },
            "headers": settings.PROVIDER_CUSTOM_HEADERS.get(provider_id, {}),
            "configured_models": self.configured_models,
            "generation_params": self.existing_config.get(
                "generation_params", settings.get_default_generation_params()
            ),
        }
        logger.debug(f"ProviderConfigDialog.get_data() is returning: {connection_data}")
        return connection_data


class ProviderConfigAsyncHandler(QtCore.QObject):
    def __init__(self, dialog: "ProviderConfigDialog"):
        super().__init__(dialog)
        self.dialog = dialog
        self.thread = None
        self.worker = None

    def _start_worker(
        self, worker_class, on_finished_slot, on_error_slot, *worker_args
    ):
        self.thread = QtCore.QThread()
        self.worker = worker_class(*worker_args)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(on_finished_slot)
        self.worker.error.connect(on_error_slot)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def fetch_models_and_info(self):
        dialog = self.dialog
        provider_id = dialog.provider_combo.currentData()
        api_key, base_url = (
            dialog.api_key_edit.text().strip(),
            dialog.base_url_edit.text().strip(),
        )
        if not api_key or (not base_url and provider_id != "gemini"):
            dialog._alert(
                translate("dialog.provider_config.warning.missing_info.title"),
                translate(
                    "dialog.provider_config.warning.missing_info.text_api_key_base_url"
                ),
            )
            return
        dialog.fetch_models_btn.setEnabled(False)
        dialog.info_button.setEnabled(False)
        dialog._set_status_indicator(
            STATUS_INDICATOR_FETCHING_COLOR,
            translate("dialog.provider_config.status.fetching_info"),
        )
        self._start_worker(
            FetchModelsWorker,
            self.on_fetch_models_finished,
            self.on_fetch_models_error,
            api_key,
            base_url,
            provider_id,
        )

    def on_fetch_models_finished(self, models_data):
        dialog = self.dialog
        dialog.fetched_models_cache = models_data
        dialog.available_models_combo.blockSignals(True)
        dialog.available_models_combo.clear()

        def clean_model_id(full_id):
            return full_id.split("/")[-1] if "/" in full_id else full_id

        sorted_models = sorted(models_data, key=lambda m: clean_model_id(m.id))
        for model in sorted_models:
            display_name = clean_model_id(model.id)
            dialog.available_models_combo.addItem(display_name, userData=model.id)
        user_entered_model_id = dialog.model_id_edit.text().strip()
        index = dialog.available_models_combo.findData(user_entered_model_id)
        if index != -1:
            dialog.available_models_combo.setCurrentIndex(index)
        dialog.available_models_combo.blockSignals(False)
        dialog._set_status_indicator(
            STATUS_INDICATOR_SUCCESS_COLOR,
            translate("dialog.provider_config.status.models_loaded"),
        )
        dialog.fetch_models_btn.setEnabled(True)
        dialog.info_button.setEnabled(True)

    def on_fetch_models_error(self, error_message):
        dialog = self.dialog
        dialog._set_status_indicator(
            STATUS_INDICATOR_FAIL_COLOR,
            translate("dialog.provider_config.status.fetch_failed"),
        )
        logger.error(f"Failed to fetch models: {error_message}", exc_info=True)
        text = translate(
            "dialog.provider_config.error.failed_to_fetch_models",
            error_message=error_message,
        )
        dialog._alert(translate("dialog.settings.fetch_models.error.generic_title"), text)
        dialog.fetch_models_btn.setEnabled(True)
        dialog.info_button.setEnabled(True)

    @wip_notification("dialog.wip.text.model_info")
    def show_combined_model_info(self):
        dialog = self.dialog
        if not (0 <= dialog.current_model_idx < len(dialog.configured_models)):
            dialog._alert(
                translate(
                    "dialog.provider_config.error.missing_info.no_model_selected"
                ),
                translate(
                    "dialog.provider_config.error.missing_info.no_model_selected"
                ),
            )
            return
        model_config = dialog.configured_models[dialog.current_model_idx]
        full_model_id = model_config.get("model_id", "").strip()
        provider_id = dialog.provider_combo.currentData()
        api_key, api_base = (
            dialog.api_key_edit.text().strip(),
            dialog.base_url_edit.text().strip(),
        )
        if not full_model_id or not provider_id:
            dialog._alert(
                translate(
                    "dialog.provider_config.error.missing_info.provider_and_model_id_required"
                ),
                translate(
                    "dialog.provider_config.error.missing_info.provider_and_model_id_required"
                ),
            )
            return
        is_cloud = (
            provider_id in CLOUD_PROVIDERS
            or provider_id not in LOCAL_PROVIDERS
        )
        if is_cloud and (not api_key or not api_base):
            dialog._alert(
                translate(
                    "dialog.provider_config.error.missing_info.api_key_and_base_url_required"
                ),
                translate(
                    "dialog.provider_config.error.missing_info.api_key_and_base_url_required"
                ),
            )
            return
        dialog.info_button.setEnabled(False)
        dialog.fetch_models_btn.setEnabled(False)
        dialog._set_status_indicator(
            STATUS_INDICATOR_FETCHING_COLOR,
            translate("dialog.provider_config.status.fetching_info"),
        )
        self._start_worker(
            ModelInfoWorker,
            self.on_model_info_finished,
            self.on_model_info_error,
            full_model_id,
            provider_id,
            api_key,
            api_base,
        )

    def on_model_info_finished(self, combined_info):
        dialog = self.dialog
        dialog._set_status_indicator(
            STATUS_INDICATOR_SUCCESS_COLOR,
            translate("dialog.provider_config.status.info_loaded"),
        )
        dialog.info_button.setEnabled(True)
        dialog.fetch_models_btn.setEnabled(True)
        pretty_response = json.dumps(combined_info, indent=4)
        title = translate(
            "dialog.provider_config.dialog.combined_info_title",
            model_id=dialog.model_id_edit.text().strip(),
        )
        result_dialog = Dialog(title, "", dialog)
        result_dialog.setFixedSize(
            COMBINED_INFO_DIALOG_MIN_WIDTH, COMBINED_INFO_DIALOG_MIN_HEIGHT
        )
        result_dialog.contentLabel.hide()
        result_dialog.cancelButton.hide()
        result_dialog.textLayout.setContentsMargins(24, 24, 24, 4)
        text_edit = TextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(pretty_response)
        text_edit.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.NoWrap)
        result_dialog.vBoxLayout.insertWidget(1, text_edit, 1)
        result_dialog.exec()

    def on_model_info_error(self, error_message):
        dialog = self.dialog
        dialog._set_status_indicator(
            STATUS_INDICATOR_FAIL_COLOR,
            translate("dialog.provider_config.status.info_fetch_failed"),
        )
        dialog.info_button.setEnabled(True)
        dialog.fetch_models_btn.setEnabled(True)
        logger.error(f"Failed to get model info: {error_message}", exc_info=True)
        text = translate(
            "dialog.provider_config.error.failed_to_get_model_info",
            error_message=error_message,
        )
        dialog._alert(translate("dialog.settings.fetch_models.error.generic_title"), text)
