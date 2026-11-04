import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    Dialog,
    FluentIcon,
    HorizontalSeparator,
    IconWidget,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
)

from ...donation import DonationConfig, DonationTarget, resolve_donation_config
from ...localization_manager import translate, auto_register


@auto_register(
    ("", "windowTitle", "dialog.donation.title"),
    ("windowTitleLabel", "text", "dialog.donation.title"),
    ("later_button", "text", "dialog.donation.button_later"),
)
class DonationDialog(Dialog):
    def __init__(self, parent=None, config: DonationConfig | None = None):
        super().__init__(translate("dialog.donation.title"), "", parent)
        self.config = resolve_donation_config(config)

        self.setFixedSize(460, 440)
        self.contentLabel.hide()
        self.yesButton.hide()
        self.cancelButton.hide()

        heart = IconWidget(FluentIcon.HEART, self)
        heart.setFixedSize(32, 32)
        self.textLayout.addWidget(heart, 0, Qt.AlignmentFlag.AlignHCenter)

        if self.config.app:
            self.textLayout.addWidget(
                self._build_target_block(
                    self.config.app, "dialog.donation.button_support"
                )
            )
        if self.config.app and self.config.core:
            self.textLayout.addWidget(HorizontalSeparator(self))
        if self.config.core:
            self.textLayout.addWidget(
                self._build_target_block(
                    self.config.core, "dialog.donation.button_support_core"
                )
            )

        self.textLayout.addStretch(1)

        self.later_button = PushButton(translate("dialog.donation.button_later"), self)
        self.later_button.clicked.connect(self.accept)
        self.buttonLayout.removeWidget(self.yesButton)
        self.buttonLayout.removeWidget(self.cancelButton)
        self.buttonLayout.addStretch(1)
        self.buttonLayout.addWidget(
            self.later_button, 0, Qt.AlignmentFlag.AlignVCenter
        )

    def _build_target_block(self, target: DonationTarget, button_key: str) -> QWidget:
        block = QWidget(self)
        block_layout = QVBoxLayout(block)
        block_layout.setContentsMargins(0, 0, 0, 0)
        block_layout.setSpacing(6)

        block_layout.addWidget(StrongBodyLabel(target.name, block))

        message_label = BodyLabel(target.message, block)
        message_label.setWordWrap(True)
        block_layout.addWidget(message_label)

        support_button = PrimaryPushButton(translate(button_key), block)
        support_button.clicked.connect(lambda: self._open(target.url))
        block_layout.addWidget(support_button, 0, Qt.AlignmentFlag.AlignRight)
        return block

    def _open(self, url: str):
        webbrowser.open(url)
        self.accept()
