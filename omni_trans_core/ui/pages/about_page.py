from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    PrimaryPushButton,
    TitleLabel,
)

from ...donation import DonationConfig


class AboutPage(QWidget):
    def __init__(
        self,
        app_name: str,
        app_version: str,
        donation: DonationConfig,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("aboutPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(10)

        layout.addWidget(TitleLabel(app_name, self))
        layout.addWidget(CaptionLabel(f"Version {app_version}", self))
        layout.addSpacing(12)
        layout.addWidget(
            BodyLabel(
                "Omni Trans Core is a reusable core for translation tools: "
                "providers, queue, cache and localization.",
                self,
            )
        )

        target = donation.app or donation.core
        if target is not None:
            layout.addSpacing(12)
            layout.addWidget(BodyLabel(target.message, self))
            support_button = PrimaryPushButton(f"Support {target.name}", self)
            support_button.clicked.connect(
                lambda: QDesktopServices.openUrl(QUrl(target.url))
            )
            layout.addWidget(support_button, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addStretch()
