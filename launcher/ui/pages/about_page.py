from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    HyperlinkButton,
    SubtitleLabel,
    TitleLabel,
)

from launcher import config


class AboutPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("aboutPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(10)

        layout.addWidget(TitleLabel("Omni Trans Launcher", self))
        layout.addWidget(CaptionLabel(f"Version {config.LAUNCHER_VERSION}", self))
        layout.addWidget(
            BodyLabel(
                "Core and application launcher for the Omni translation suite.",
                self,
            )
        )
        layout.addSpacing(12)

        card = CardWidget(self)
        card.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(8)
        card_layout.addWidget(SubtitleLabel("Links", card))

        github = HyperlinkButton(card)
        github.setText("GitHub")
        github.setUrl(config.SOCIAL_CONFIG["github"]["link"])
        card_layout.addWidget(github, 0, Qt.AlignmentFlag.AlignLeft)

        telegram = HyperlinkButton(card)
        telegram.setText("Telegram")
        telegram.setUrl(config.SOCIAL_CONFIG["telegram"]["link"])
        card_layout.addWidget(telegram, 0, Qt.AlignmentFlag.AlignLeft)

        card_layout.addWidget(
            CaptionLabel("License: GPLv3", card),
            0,
            Qt.AlignmentFlag.AlignLeft,
        )

        layout.addWidget(card)
        layout.addStretch()
