import logging

from PySide6 import QtCore, QtWidgets
from qfluentwidgets import BodyLabel, CardWidget, ComboBox, PushButton

from ... import settings
from ...localization_manager import loc_man, translate
from ..dialogs import ManageLanguagesDialog

logger = logging.getLogger("CORE_UI.widgets")


class _BaseLanguageWidget(CardWidget):
    language_changed = QtCore.Signal(str)

    def __init__(self, title_key: str, lang_type: str, parent=None):
        super().__init__(parent)
        if lang_type not in ["source", "target"]:
            raise ValueError("lang_type must be 'source' or 'target'")
        self.title_key = title_key
        self.lang_type = lang_type
        self.config_key = (
            "available_source_languages"
            if lang_type == "source"
            else "target_languages"
        )
        self.selected_lang_key = (
            "selected_source_language"
            if lang_type == "source"
            else "selected_target_language"
        )
        self.init_ui()
        loc_man.register(self.title_label, "text", self.title_key)
        loc_man.register(
            self.manage_button, "text", "widget.language.manage_button"
        )
        self.connect_signals()
        self.update_language_combo()
        loc_man.language_changed.connect(self.update_language_combo)

    def init_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(10)
        self.title_label = BodyLabel(self)
        self.combo = ComboBox(self)
        self.manage_button = PushButton(self)
        layout.addWidget(self.title_label)
        layout.addWidget(self.combo, 1)
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
            else:
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
            logger.info(
                "Selected %s language changed to: '%s'", self.lang_type, lang_name
            )
        self.language_changed.emit(lang_name)

    @QtCore.Slot()
    def _open_manage_dialog(self):
        dialog = ManageLanguagesDialog(self.lang_type.capitalize(), self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.update_language_combo()


class SourceLanguageWidget(_BaseLanguageWidget):
    def __init__(self, parent=None):
        super().__init__("widget.language.source_title", "source", parent)


class TargetLanguageWidget(_BaseLanguageWidget):
    def __init__(self, parent=None):
        super().__init__("widget.language.target_title", "target", parent)
