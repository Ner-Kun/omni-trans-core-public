from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel,
    FluentIcon,
    SettingCardGroup,
    SwitchSettingCard,
    TitleLabel,
)

from launcher.utils.settings import LauncherSettings


class SettingsPage(QWidget):
    tray_setting_changed = Signal(bool)

    def __init__(self, settings: LauncherSettings, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self.settings = settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(12)

        layout.addWidget(TitleLabel("Settings", self))
        layout.addWidget(CaptionLabel("Launcher behavior", self))

        launch_group = SettingCardGroup("Launch", self)
        self.close_card = SwitchSettingCard(
            FluentIcon.POWER_BUTTON,
            "Close after launch",
            "Close the launcher when the application window is ready.",
            None,
            launch_group,
        )
        self.close_card.switchButton.setChecked(settings.close_after_launch)
        self.close_card.switchButton.checkedChanged.connect(
            self._on_close_after_launch_changed
        )
        launch_group.addSettingCard(self.close_card)

        self.tray_card = SwitchSettingCard(
            FluentIcon.MINIMIZE,
            "Minimize to tray",
            "Keep the launcher running in the system tray when you close it.",
            None,
            launch_group,
        )
        self.tray_card.switchButton.setChecked(settings.minimize_to_tray)
        self.tray_card.switchButton.checkedChanged.connect(
            self._on_minimize_to_tray_changed
        )
        launch_group.addSettingCard(self.tray_card)
        layout.addWidget(launch_group)

        startup_group = SettingCardGroup("Startup", self)
        self.updates_card = SwitchSettingCard(
            FluentIcon.SYNC,
            "Check for updates on startup",
            "Check for new releases when the launcher starts. "
            "Use Refresh to check manually.",
            None,
            startup_group,
        )
        self.updates_card.switchButton.setChecked(
            settings.check_updates_on_startup
        )
        self.updates_card.switchButton.checkedChanged.connect(
            self._on_check_updates_changed
        )
        startup_group.addSettingCard(self.updates_card)

        self.remember_card = SwitchSettingCard(
            FluentIcon.HISTORY,
            "Remember last selected app",
            "Open the launcher with the last selected application.",
            None,
            startup_group,
        )
        self.remember_card.switchButton.setChecked(settings.remember_last_app)
        self.remember_card.switchButton.checkedChanged.connect(
            self._on_remember_last_app_changed
        )
        startup_group.addSettingCard(self.remember_card)
        layout.addWidget(startup_group)

        layout.addStretch()

    def _on_close_after_launch_changed(self, checked: bool) -> None:
        self.settings.close_after_launch = checked
        self.settings.save()

    def _on_minimize_to_tray_changed(self, checked: bool) -> None:
        self.settings.minimize_to_tray = checked
        self.settings.save()
        self.tray_setting_changed.emit(checked)

    def _on_check_updates_changed(self, checked: bool) -> None:
        self.settings.check_updates_on_startup = checked
        self.settings.save()

    def _on_remember_last_app_changed(self, checked: bool) -> None:
        self.settings.remember_last_app = checked
        if not checked:
            self.settings.last_selected_app = ""
        self.settings.save()
