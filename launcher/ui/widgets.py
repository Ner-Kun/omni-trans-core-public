from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    InfoBadge,
    InfoLevel,
)

from launcher.models.app_model import AppData


class AppListItem(QWidget):
    """Compact row for the application list."""

    def __init__(self, app: AppData, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background: transparent;")
        self.setMinimumHeight(58)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)

        self.icon_label = QLabel(self)
        self.icon_label.setFixedSize(36, 36)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = app.icon if not app.icon.isNull() else FluentIcon.APPLICATION.icon()
        self.icon_label.setPixmap(icon.pixmap(QSize(32, 32)))
        layout.addWidget(self.icon_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        self.name_label = BodyLabel(app.name, self)
        self.name_label.setStyleSheet("font-weight: 600;")
        self.version_label = CaptionLabel(self._version_text(app), self)
        text_layout.addWidget(self.name_label)
        text_layout.addWidget(self.version_label)
        layout.addLayout(text_layout, 1)

        self.status_badge = InfoBadge.info("", self)
        layout.addWidget(self.status_badge)
        self.update_state(app)

    def update_state(self, app: AppData) -> None:
        self.version_label.setText(self._version_text(app))
        level, text = self._status(app)
        self.status_badge.setLevel(level)
        self.status_badge.setText(text)

    @staticmethod
    def _version_text(app: AppData) -> str:
        if not app.is_local:
            return f"v{app.latest_version} available"
        if app.update_available:
            return f"v{app.local_version} → v{app.latest_version}"
        return f"v{app.local_version}"

    @staticmethod
    def _status(app: AppData) -> tuple[InfoLevel, str]:
        if app.is_running:
            return InfoLevel.SUCCESS, "Running"
        if app.is_launching:
            return InfoLevel.INFOAMTION, "Launching"
        if app.is_critical and app.update_available:
            return InfoLevel.ERROR, "Critical"
        if app.update_available:
            return InfoLevel.WARNING, "Update"
        if app.is_local:
            return InfoLevel.SUCCESS, "Installed"
        return InfoLevel.INFOAMTION, "Available"
