import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import (
    Dialog,
    LineEdit,
    ListWidget,
    MessageBox,
    PushButton,
)

from ...localization_manager import translate, auto_register
from ... import settings

logger = logging.getLogger('CORE_UI.dialogs')

@auto_register(
    ("", "windowTitle", "dialog.manage_languages.title", ["language_type"]),
    ("windowTitleLabel", "text", "dialog.manage_languages.title", ["language_type"]),
    ("lang_input", "placeholderText", "dialog.manage_languages.placeholder.enter_language"),
    ("add_button", "text", "dialog.manage_languages.button.add"),
    ("remove_button", "text", "dialog.manage_languages.button.remove"),
)
class ManageLanguagesDialog(Dialog):
    def __init__(self, language_type="Target", parent=None):
        super().__init__(
            translate("dialog.manage_languages.title", language_type=language_type),
            "",
            parent,
        )
        self.setFixedSize(460, 520)
        self.contentLabel.hide()
        self.language_type = language_type
        if self.language_type == "Target":
            self.config_key = "target_languages"
        else:
            self.config_key = "available_source_languages"
        self.languages = list(settings.current_settings.get(self.config_key, []))

        self.list_widget = ListWidget(self)
        self.list_widget.addItems(self.languages)
        self.textLayout.addWidget(self.list_widget)

        input_layout = QHBoxLayout()
        self.lang_input = LineEdit(self)
        input_layout.addWidget(self.lang_input, 1)
        self.add_button = PushButton(
            translate("dialog.manage_languages.button.add"), self
        )
        self.add_button.clicked.connect(self.add_language)
        input_layout.addWidget(self.add_button)
        self.textLayout.addLayout(input_layout)

        self.remove_button = PushButton(
            translate("dialog.manage_languages.button.remove"), self
        )
        self.remove_button.clicked.connect(self.remove_language)
        self.textLayout.addWidget(self.remove_button, 0, Qt.AlignmentFlag.AlignLeft)

    def _save_and_update_settings(self):
        settings.current_settings[self.config_key] = self.languages
        if self.language_type == "Target":
            selected_lang = settings.current_settings.get(
                "selected_target_language", ""
            )
            if self.languages and selected_lang not in self.languages:
                settings.current_settings["selected_target_language"] = self.languages[
                    0
                ]
            elif not self.languages:
                settings.current_settings["selected_target_language"] = ""
        else:
            selected_lang = settings.current_settings.get(
                "selected_source_language", ""
            )
            if self.languages and selected_lang not in self.languages:
                settings.current_settings["selected_source_language"] = self.languages[
                    0
                ]
        settings.save_settings()
        logger.info(
            f"{self.language_type} languages updated and saved: {self.languages}"
        )

    def add_language(self):
        lang_name = self.lang_input.text().strip()
        if lang_name and lang_name not in self.languages:
            self.languages.append(lang_name)
            self.languages.sort()
            self.list_widget.clear()
            self.list_widget.addItems(self.languages)
            self.lang_input.clear()
            self._save_and_update_settings()
        elif lang_name in self.languages:
            title = translate("dialog.manage_languages.error.duplicate.title")
            text = translate(
                "dialog.manage_languages.error.duplicate.text", lang_name=lang_name
            )
            MessageBox(title, text, self).exec()
        elif not lang_name:
            title = translate("dialog.manage_languages.error.empty.title")
            text = translate("dialog.manage_languages.error.empty.text")
            MessageBox(title, text, self).exec()

    def remove_language(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return
        if (
            self.language_type == "Source"
            and len(self.languages) - len(selected_items) < 1
        ):
            title = translate("dialog.manage_languages.error.cannot_remove.title")
            text = translate("dialog.manage_languages.error.cannot_remove.text")
            MessageBox(title, text, self).exec()
            return
        for item in selected_items:
            lang_to_remove = item.text()
            if lang_to_remove in self.languages:
                self.languages.remove(lang_to_remove)
        self.list_widget.clear()
        self.list_widget.addItems(self.languages)
        self._save_and_update_settings()

    def accept(self):
        if self.lang_input.text().strip():
            self.add_language()
        super().accept()
