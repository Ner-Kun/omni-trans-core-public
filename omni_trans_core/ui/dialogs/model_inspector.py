from PySide6 import QtWidgets, QtCore, QtGui
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    Dialog,
    StrongBodyLabel,
    TextEdit,
    isDarkTheme,
)

from ...localization_manager import loc_man, translate, auto_register
from ... import settings

DIALOG_WIDTH = 760
DIALOG_HEIGHT = 680
PROXY_BADGE_COLOR = "#7aa2f7"


@auto_register(
    ("", "windowTitle", "dialog.model_inspector.title"),
    ("prompt_label", "text", "dialog.model_inspector.label.last_prompt"),
    ("tokens_header", "text", "dialog.model_inspector.group.usage_metadata"),
    ("thinking_header", "text", "dialog.model_inspector.group.thinking"),
    ("processed_translation_label", "text", "dialog.model_inspector.label.final_translation"),
)
class ModelInspectorDialog(Dialog):
    def __init__(self, parent=None):
        super().__init__(translate("dialog.model_inspector.title"), "", parent)
        self._last_data = None
        self.setFixedSize(DIALOG_WIDTH, DIALOG_HEIGHT)
        self.setModal(False)
        self._init_window_chrome()
        self._build_ui()
        self.clear_data()
        loc_man.language_changed.connect(self._refresh_dynamic_localization)

    def _init_window_chrome(self):
        """Turn the Fluent dialog into a floating tool window.

        The inspector is toggled from the menu, so it keeps a draggable title bar
        with a close button instead of the OK/Cancel footer the base dialog adds.
        """
        self.titleBar.show()
        self.titleBar.raise_()
        self.windowTitleLabel.setFixedHeight(self.titleBar.height())
        self.windowTitleLabel.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.windowTitleLabel.setContentsMargins(16, 0, 0, 0)
        # The stock title bar button glyph is black and disappears on the dark
        # dialog background, so paint it with the theme's foreground color.
        self.titleBar.closeBtn.setNormalColor(
            QtGui.QColor("#ffffff" if isDarkTheme() else "#000000")
        )
        self.titleLabel.hide()
        self.contentLabel.hide()
        self.yesButton.hide()
        self.cancelButton.hide()
        self.buttonGroup.hide()
        self.textLayout.setContentsMargins(24, 8, 24, 24)

    def _create_section(self) -> tuple[CardWidget, StrongBodyLabel, TextEdit]:
        card = CardWidget(self)
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(8)
        header = StrongBodyLabel(card)
        editor = TextEdit(card)
        editor.setReadOnly(True)
        card_layout.addWidget(header)
        card_layout.addWidget(editor, 1)
        return card, header, editor

    def _build_ui(self):
        header_row = QtWidgets.QHBoxLayout()
        header_row.setSpacing(12)
        self.model_name_label = BodyLabel(self)
        self.proxy_info_label = CaptionLabel(self)
        self.proxy_info_label.setStyleSheet(
            f"color: {PROXY_BADGE_COLOR}; font-size: 11px;"
        )
        header_row.addWidget(self.model_name_label)
        header_row.addStretch(1)
        header_row.addWidget(self.proxy_info_label)
        self.textLayout.addLayout(header_row)

        self.prompt_card, self.prompt_label, self.prompt_text_edit = self._create_section()
        self.textLayout.addWidget(self.prompt_card, 2)

        self.tokens_card = self._create_tokens_card()
        self.textLayout.addWidget(self.tokens_card, 0)

        (
            self.thinking_card,
            self.thinking_header,
            self.thinking_text_edit,
        ) = self._create_section()
        self.thinking_card.setVisible(False)
        self.textLayout.addWidget(self.thinking_card, 3)

        (
            self.processed_translation_card,
            self.processed_translation_label,
            self.processed_translation_text_edit,
        ) = self._create_section()
        self.textLayout.addWidget(self.processed_translation_card, 1)

    def _create_tokens_card(self) -> CardWidget:
        card = CardWidget(self)
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(8)
        self.tokens_header = StrongBodyLabel(card)
        card_layout.addWidget(self.tokens_header)

        tokens_row = QtWidgets.QHBoxLayout()
        tokens_row.setSpacing(8)
        self.prompt_tokens_label = BodyLabel(card)
        self.thinking_tokens_label = BodyLabel(card)
        self.response_tokens_label = BodyLabel(card)
        self.total_tokens_label = BodyLabel(card)
        for index, label in enumerate(
            (
                self.prompt_tokens_label,
                self.thinking_tokens_label,
                self.response_tokens_label,
                self.total_tokens_label,
            )
        ):
            if index:
                tokens_row.addStretch(1)
            tokens_row.addWidget(label)
        card_layout.addLayout(tokens_row)
        return card

    def _refresh_dynamic_localization(self):
        if self._last_data:
            self.update_data(*self._last_data)
        else:
            self.clear_data()
            na = translate("dialog.model_inspector.label.na")
            self.model_name_label.setText(
                translate("dialog.model_inspector.label.model_name", model=na)
            )

    @QtCore.Slot(str, str, str, str, dict, str, bool)
    def update_data(
        self, model_name, prompt, final_translation_text, thinking_text, usage_metadata, proxy_ip="", proxy_used=False
    ):
        self._last_data = (
            model_name,
            prompt,
            final_translation_text,
            thinking_text,
            usage_metadata,
            proxy_ip,
            proxy_used,
        )
        na = translate("dialog.model_inspector.label.na")
        self.model_name_label.setText(
            translate("dialog.model_inspector.label.model_name", model=model_name or na)
        )
        # Update proxy info
        if proxy_used and proxy_ip:
            self.proxy_info_label.setText(f"🔒 Proxy: {proxy_ip}")
            self.proxy_info_label.setVisible(True)
        else:
            self.proxy_info_label.setText("No proxy")
            self.proxy_info_label.setVisible(True)
        self.prompt_text_edit.setPlainText(prompt)
        self.processed_translation_text_edit.setPlainText(final_translation_text)
        prompt_tokens = usage_metadata.get("prompt", na)
        thoughts_tokens = usage_metadata.get("thoughts", na)
        candidates_tokens = usage_metadata.get("candidates", na)
        total_tokens = usage_metadata.get("total", na)
        self.prompt_tokens_label.setText(
            translate(
                "dialog.model_inspector.label.prompt_tokens", tokens=prompt_tokens
            )
        )
        self.thinking_tokens_label.setText(
            translate(
                "dialog.model_inspector.label.thinking_tokens", tokens=thoughts_tokens
            )
        )
        self.response_tokens_label.setText(
            translate(
                "dialog.model_inspector.label.response_tokens", tokens=candidates_tokens
            )
        )
        self.total_tokens_label.setText(
            translate("dialog.model_inspector.label.total_tokens", tokens=total_tokens)
        )
        self.thinking_tokens_label.setVisible("thoughts" in usage_metadata)
        if thinking_text and settings.current_settings.get(
            "enable_model_thinking", True
        ):
            self.thinking_card.setVisible(True)
            self.thinking_text_edit.setPlainText(thinking_text)
        else:
            self.thinking_card.setVisible(False)
            self.thinking_text_edit.clear()

    def clear_data(self):
        self._last_data = None
        self.prompt_text_edit.clear()
        self.processed_translation_text_edit.clear()
        self.thinking_text_edit.clear()
        self.thinking_card.setVisible(False)
        self.proxy_info_label.setText("")
        self.proxy_info_label.setVisible(False)
        na = translate("dialog.model_inspector.label.na")
        self.model_name_label.setText(
            translate("dialog.model_inspector.label.model_name", model=na)
        )
        self.prompt_tokens_label.setText(
            translate("dialog.model_inspector.label.prompt_tokens", tokens=na)
        )
        self.thinking_tokens_label.setText(
            translate("dialog.model_inspector.label.thinking_tokens", tokens=na)
        )
        self.response_tokens_label.setText(
            translate("dialog.model_inspector.label.response_tokens", tokens=na)
        )
        self.total_tokens_label.setText(
            translate("dialog.model_inspector.label.total_tokens", tokens=na)
        )

    def closeEvent(self, event):
        self.hide()
        event.ignore()
