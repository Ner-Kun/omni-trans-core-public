from PySide6.QtCore import QTimer, Slot
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QMenu,
    QSystemTrayIcon,
)
from qfluentwidgets import (
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    MessageBox,
    MSFluentWindow,
    NavigationItemPosition,
)

from launcher import config
from launcher.controllers.catalog_controller import CatalogController
from launcher.models.app_model import AppData
from launcher.models.catalog_model import CatalogModel
from launcher.ui.dialogs import DonationDialog
from launcher.ui.pages.about_page import AboutPage
from launcher.ui.pages.apps_page import AppsPage
from launcher.ui.pages.settings_page import SettingsPage
from launcher.utils.links import detect_donate_link
from launcher.utils.settings import LauncherSettings


class LauncherWindow(MSFluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{config.APP_NAME} {config.LAUNCHER_VERSION}")
        self.resize(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
        self.setMinimumSize(900, 600)
        self.setWindowIcon(FluentIcon.APPLICATION.icon())
        self.setStyleSheet("LauncherWindow { background-color: #1a1a1e; }")

        self.settings = LauncherSettings()
        self._force_quit = False

        self.model = CatalogModel(self)
        self.controller = CatalogController(self.model, self)

        self.donate_url, self.donate_tooltip = detect_donate_link()
        self._launcher_update_prompted = False

        self.apps_page = AppsPage(
            self.model,
            self.controller,
            self.donate_url,
            self.donate_tooltip,
            remembered_app=(
                self.settings.last_selected_app
                if self.settings.remember_last_app
                else ""
            ),
            parent=self,
        )
        self.settings_page = SettingsPage(self.settings, self)
        self.about_page = AboutPage(self)

        self.addSubInterface(
            self.apps_page,
            FluentIcon.APPLICATION,
            "Applications",
        )
        self.addSubInterface(
            self.settings_page,
            FluentIcon.SETTING,
            "Settings",
            position=NavigationItemPosition.BOTTOM,
        )
        self.addSubInterface(
            self.about_page,
            FluentIcon.INFO,
            "About",
            position=NavigationItemPosition.BOTTOM,
        )

        self._tray_icon = QSystemTrayIcon(FluentIcon.APPLICATION.icon(), self)
        self._tray_icon.setToolTip(config.APP_NAME)
        tray_menu = QMenu(self)
        tray_menu.addAction("Show launcher").triggered.connect(
            self._restore_from_tray
        )
        tray_menu.addAction("Quit").triggered.connect(self._quit_from_tray)
        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._update_tray_icon()

        self.controller.launch_started.connect(self._on_launch_started)
        self.controller.app_window_ready.connect(self._on_app_window_ready)
        self.controller.app_window_timeout.connect(self._on_app_window_timeout)
        self.controller.app_launch_failed.connect(self._on_app_launch_failed)
        self.controller.launcher_update_started.connect(
            self._on_launcher_update_started
        )
        self.controller.nag_required.connect(self._on_nag_required)
        self.model.catalog_loaded.connect(self._on_catalog_loaded)
        self.model.app_selected.connect(self._on_app_selected)
        self.settings_page.tray_setting_changed.connect(self._update_tray_icon)

        self.controller.app_manager.save_donate_link_preference(self.donate_url)

        self._state_timer = QTimer(self)
        self._state_timer.setInterval(3000)
        self._state_timer.timeout.connect(self.controller.refresh_running_states)
        self._state_timer.start()

        QTimer.singleShot(
            100,
            lambda: self.controller.load_catalog(
                check_updates=self.settings.check_updates_on_startup
            ),
        )
        QTimer.singleShot(600, self._check_launcher_nag)

    @Slot(list)
    def _on_catalog_loaded(self, _apps) -> None:
        if not self.controller.last_updates_checked:
            return

        if self._launcher_update_prompted:
            return

        info = self.controller.app_manager.get_launcher_update_info()
        if not info:
            return

        self._launcher_update_prompted = True
        new_version = info.get("pending_update_version", "?")

        box = MessageBox(
            "Launcher update",
            f"A new version (v{new_version}) is available.\n"
            "Update and restart now?",
            self,
        )
        box.yesButton.setText("Update")
        box.cancelButton.setText("Later")

        if box.exec() == QDialog.DialogCode.Accepted:
            self.controller.update_launcher(info)

    @Slot(AppData)
    def _on_app_selected(self, app: AppData) -> None:
        if self.settings.remember_last_app:
            if self.settings.last_selected_app != app.folder_name:
                self.settings.last_selected_app = app.folder_name
                self.settings.save()
        elif self.settings.last_selected_app:
            self.settings.last_selected_app = ""
            self.settings.save()

    def _check_launcher_nag(self) -> None:
        show, count = self.controller.app_manager.register_launch_and_check_nag(
            "launcher", is_launcher=True
        )
        if show:
            DonationDialog(self, config.APP_NAME, count, self.donate_url).exec()

    @Slot(str, int)
    def _on_nag_required(self, app_name: str, count: int) -> None:
        DonationDialog(self, app_name, count, self.donate_url).exec()

    @Slot(str)
    def _on_launch_started(self, app_name: str) -> None:
        InfoBar.info(
            "Launching",
            app_name,
            duration=3000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self,
        )

    @Slot(str)
    def _on_app_window_ready(self, folder_name: str) -> None:
        app_name = self.controller.app_manager.get_app_entry(folder_name).get(
            "name", folder_name
        )

        if self.settings.close_after_launch:
            if self.settings.minimize_to_tray and self._tray_icon.isVisible():
                self._hide_to_tray()
            else:
                self._quit_application()
            return

        InfoBar.success(
            "Running",
            f"{app_name} is ready.",
            duration=3000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self,
        )
        self.controller.refresh_running_states()

    @Slot(str)
    def _on_app_window_timeout(self, folder_name: str) -> None:
        app_name = self.controller.app_manager.get_app_entry(folder_name).get(
            "name", folder_name
        )
        InfoBar.warning(
            "Still starting",
            f"{app_name} has not opened its window yet.",
            duration=5000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self,
        )

    @Slot(str, str)
    def _on_app_launch_failed(self, folder_name: str, message: str) -> None:
        box = MessageBox("Launch failed", message, self)
        box.hideCancelButton()
        box.yesButton.setText("OK")
        box.exec()

    @Slot()
    def _on_launcher_update_started(self) -> None:
        self._quit_application()

    def _update_tray_icon(self, enabled: bool | None = None) -> None:
        if enabled is None:
            enabled = self.settings.minimize_to_tray

        if enabled and QSystemTrayIcon.isSystemTrayAvailable():
            self._tray_icon.show()
        else:
            self._tray_icon.hide()

    def _hide_to_tray(self) -> None:
        self.hide()
        if self._tray_icon.isVisible():
            self._tray_icon.showMessage(
                config.APP_NAME,
                "Still running in the tray.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )

    @Slot()
    def _restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    @Slot(object)
    def _on_tray_activated(
        self, reason: QSystemTrayIcon.ActivationReason
    ) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._restore_from_tray()

    @Slot()
    def _quit_from_tray(self) -> None:
        self._force_quit = True
        if self.controller.is_busy():
            self._restore_from_tray()
            self.close()
        else:
            self._quit_application()

    def _quit_application(self) -> None:
        self._state_timer.stop()
        self.apps_page.stop_animations()
        self._tray_icon.hide()
        QApplication.quit()

    def closeEvent(self, event):
        if (
            self.settings.minimize_to_tray
            and not self._force_quit
            and self._tray_icon.isVisible()
        ):
            self._hide_to_tray()
            event.ignore()
            return

        if self.controller.is_busy():
            box = MessageBox(
                "Operation in progress",
                "An install or update is running. Quit anyway?",
                self,
            )
            box.yesButton.setText("Quit")
            box.cancelButton.setText("Stay")
            if box.exec() != QDialog.DialogCode.Accepted:
                self._force_quit = False
                event.ignore()
                return

        self._state_timer.stop()
        self.apps_page.stop_animations()
        self._tray_icon.hide()
        super().closeEvent(event)
