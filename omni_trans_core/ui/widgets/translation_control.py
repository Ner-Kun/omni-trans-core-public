import logging
from functools import wraps

from PySide6 import QtCore, QtWidgets
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
)

from ... import settings
from ...interfaces import IControlWidgetActions, TranslatableItem
from ...localization_manager import auto_register, loc_man, translate
from ...utils import DebounceTimer
from ..animations import UIAnimator

logger = logging.getLogger("CORE_UI.widgets")

EDIT_DEBOUNCE_INTERVAL_MS = 1000
EDITING_STATUS_FLASH_DURATION_MS = 800
EDITING_STATUS_FLASH_COLOR = "#f1fa8c"


@auto_register(
    ("title_label", "text", "widget.control.group_title"),
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
class TranslationControlWidget(CardWidget):
    item_edited = QtCore.Signal(str, str)

    def __init__(self, actions_handler: IControlWidgetActions, parent=None):
        super().__init__(parent)
        self.actions_handler = actions_handler
        self.current_item_id = None
        self.current_translation_in_editor = None
        self.debounce_timer = DebounceTimer(
            self._apply_edited_translation, EDIT_DEBOUNCE_INTERVAL_MS, self
        )
        self._init_ui()
        self._connect_signals()
        loc_man.language_changed.connect(self._refresh_dynamic_localization)
        initial_lang = settings.current_settings.get("selected_target_language", "")
        self.set_active_language(initial_lang)

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        self.title_label = StrongBodyLabel(self)
        layout.addWidget(self.title_label)

        original_row = QtWidgets.QHBoxLayout()
        self.original_text_label = BodyLabel(self)
        self.orig_label = BodyLabel(self)
        self.orig_label.setWordWrap(True)
        self.save_status_label = BodyLabel(self)
        self.save_status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        original_row.addWidget(self.original_text_label)
        original_row.addWidget(self.orig_label, 1)
        layout.addLayout(original_row)

        translation_row = QtWidgets.QHBoxLayout()
        self.translation_label = BodyLabel(self)
        self.trans_edit = LineEdit(self)
        translation_row.addWidget(self.translation_label)
        translation_row.addWidget(self.trans_edit, 1)
        layout.addLayout(translation_row)

        status_row = QtWidgets.QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.addStretch()
        status_row.addWidget(self.save_status_label)
        layout.addLayout(status_row)

        action_buttons_layout = QtWidgets.QVBoxLayout()
        action_buttons_layout.setContentsMargins(0, 0, 0, 0)
        action_buttons_layout.setSpacing(6)
        self.regenerate_btn = PushButton(self)
        self.translate_selected_btn = PrimaryPushButton(self)
        self.translate_all_btn = PushButton(self)
        self.delete_selected_btn = PushButton(self)
        self.delete_all_btn = PushButton(self)
        regenerate_row = QtWidgets.QHBoxLayout()
        regenerate_row.setContentsMargins(0, 0, 0, 0)
        regenerate_row.addWidget(self.regenerate_btn)
        regenerate_row.addWidget(self.translate_all_btn)
        regenerate_row.addStretch()
        action_buttons_layout.addLayout(regenerate_row)
        translate_row = QtWidgets.QHBoxLayout()
        translate_row.setContentsMargins(0, 0, 0, 0)
        translate_row.addWidget(self.translate_selected_btn)
        translate_row.addStretch()
        action_buttons_layout.addLayout(translate_row)
        delete_row = QtWidgets.QHBoxLayout()
        delete_row.setContentsMargins(0, 0, 0, 0)
        delete_row.addWidget(self.delete_selected_btn)
        delete_row.addWidget(self.delete_all_btn)
        delete_row.addStretch()
        action_buttons_layout.addLayout(delete_row)
        layout.addLayout(action_buttons_layout)

        self.clear_selection()
        self.translate_all_btn.setEnabled(False)
        self.delete_all_btn.setEnabled(False)

    def _require_items(requirement_type: str):
        def decorator(func):
            @wraps(func)
            def wrapper(self, *args, **kwargs):
                items = []
                if requirement_type == "selected":
                    items = self.actions_handler.get_selected_items()
                    if not items:
                        title = translate("widget.control.error.no_selection.title")
                        text = translate("widget.control.error.no_selection.text")
                        self.actions_handler.show_info_message(title, text)
                        return
                elif requirement_type == "all":
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
            self.save_status_label.setText(
                translate("widget.control.status_no_selection")
            )
        initial_lang = settings.current_settings.get("selected_target_language", "")
        self.set_active_language(initial_lang)

    def _connect_signals(self):
        self.trans_edit.textChanged.connect(self._on_text_changed)
        self.trans_edit.editingFinished.connect(self.on_before_save)
        self.actions_handler.data_availability_changed.connect(
            self.translate_all_btn.setEnabled
        )
        self.actions_handler.data_availability_changed.connect(
            self.delete_all_btn.setEnabled
        )
        self.regenerate_btn.clicked.connect(self._on_regenerate)
        self.translate_selected_btn.clicked.connect(self._on_translate_selected)
        self.translate_all_btn.clicked.connect(self._on_translate_all)
        self.delete_selected_btn.clicked.connect(self._on_delete)
        self.delete_all_btn.clicked.connect(self._on_delete_all)

    def set_active_language(self, lang_name: str):
        if lang_name:
            self.translation_label.setText(
                translate(
                    "widget.control.translation_label_template", lang_name=lang_name
                )
            )
        else:
            self.translation_label.setText(
                translate("widget.control.translation_label_default")
            )

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
        UIAnimator.flash_status_label(
            self.save_status_label, translate("widget.control.status_saved")
        )

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
        self.save_status_label.setText(
            translate("widget.control.status_no_selection")
        )
        self.block_all_signals(False)

    def update_item_display(self, item_id: str, new_text: str):
        if self.current_item_id == item_id:
            self.trans_edit.blockSignals(True)
            self.trans_edit.setText(new_text)
            self.trans_edit.blockSignals(False)
            self.current_translation_in_editor = new_text
            UIAnimator.flash_status_label(
                self.save_status_label, translate("widget.control.status_saved")
            )

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
                duration_ms=EDITING_STATUS_FLASH_DURATION_MS,
            )
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
            UIAnimator.flash_status_label(
                self.save_status_label, translate("widget.control.status_saved")
            )

    @QtCore.Slot()
    @_require_items("selected")
    def _on_translate_selected(self, items: list[TranslatableItem]):
        self.actions_handler.handle_translation_request(items, force_regen=False)

    @QtCore.Slot()
    @_require_items("all")
    def _on_translate_all(self, items: list[TranslatableItem]):
        self.actions_handler.handle_translation_request(items, force_regen=False)

    @QtCore.Slot()
    @_require_items("selected")
    def _on_regenerate(self, items: list[TranslatableItem]):
        self.actions_handler.handle_translation_request(items, force_regen=True)

    @QtCore.Slot()
    @_require_items("selected")
    def _on_delete(self, items: list[TranslatableItem]):
        self.actions_handler.handle_deletion_request(items)

    @QtCore.Slot()
    @_require_items("all")
    def _on_delete_all(self, items: list[TranslatableItem]):
        self.actions_handler.handle_deletion_request(items)
