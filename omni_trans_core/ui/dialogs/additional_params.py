from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import Dialog, PushButton, StrongBodyLabel, TextEdit

from ...localization_manager import translate, auto_register


@auto_register(
    ("", "windowTitle", "dialog.additional_params.title"),
    ("windowTitleLabel", "text", "dialog.additional_params.title"),
    ("insert_presets_btn", "text", "dialog.additional_params.button.insert_presets"),
    ("include_body_title", "text", "dialog.additional_params.group.include_body"),
    ("include_body_edit", "placeholderText", "dialog.additional_params.placeholder.include_body"),
    ("exclude_body_title", "text", "dialog.additional_params.group.exclude_body"),
    ("exclude_body_edit", "placeholderText", "dialog.additional_params.placeholder.exclude_body"),
    ("include_headers_title", "text", "dialog.additional_params.group.include_headers"),
    ("include_headers_edit", "placeholderText", "dialog.additional_params.placeholder.include_headers"),
)
class AdditionalParametersDialog(Dialog):
    def __init__(self, params: dict[str, str], parent=None):
        super().__init__(translate("dialog.additional_params.title"), "", parent)
        self.setFixedSize(660, 640)
        self.contentLabel.hide()

        presets_layout = QHBoxLayout()
        self.insert_presets_btn = PushButton(self)
        presets_layout.addWidget(self.insert_presets_btn)
        presets_layout.addStretch(1)
        self.textLayout.addLayout(presets_layout)

        (
            self.include_body_group,
            self.include_body_title,
            self.include_body_edit,
        ) = self._add_section(params.get("include_body_params", ""))
        (
            self.exclude_body_group,
            self.exclude_body_title,
            self.exclude_body_edit,
        ) = self._add_section(params.get("exclude_body_params", ""))
        (
            self.include_headers_group,
            self.include_headers_title,
            self.include_headers_edit,
        ) = self._add_section(params.get("include_headers", ""))

        self.insert_presets_btn.clicked.connect(self._insert_presets)

    def _add_section(self, text: str):
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = StrongBodyLabel("", container)
        title.setWordWrap(True)
        edit = TextEdit(container)
        edit.setPlainText(text)

        layout.addWidget(title)
        layout.addWidget(edit, 1)
        self.textLayout.addWidget(container, 1)
        return container, title, edit

    def _insert_presets(self):
        header_preset = "X-Enable-Thinking: true"
        body_preset = "chat_template_kwargs:\n  thinking: true"

        self.include_headers_edit.setPlainText(header_preset)
        self.include_body_edit.setPlainText(body_preset)

    def get_data(self) -> dict[str, str]:
        return {
            "include_body_params": self.include_body_edit.toPlainText(),
            "exclude_body_params": self.exclude_body_edit.toPlainText(),
            "include_headers": self.include_headers_edit.toPlainText(),
        }
