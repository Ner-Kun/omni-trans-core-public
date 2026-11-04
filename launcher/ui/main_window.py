import webbrowser

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QPushButton,
    QMessageBox,
    QTextBrowser,
)
from PySide6.QtCore import Qt, QTimer, QSize, QLocale, QTimeZone, Slot
from rich.console import Console

from launcher import config
from launcher.ui.widgets import SmartButton, AnimatedIconButton
from launcher.ui.dialogs import DonationDialog, CriticalUpdateDialog
from launcher.models.app_model import AppData
from launcher.models.catalog_model import CatalogModel
from launcher.controllers.catalog_controller import CatalogController
from launcher.utils.icon_manager import IconManager
from launcher.utils.animations import DonateAnimator


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.console = Console()
        self.console.log("Starting Main Window...")

        self.setWindowTitle(f"Omni Trans Launcher - v{config.LAUNCHER_VERSION}")
        self.resize(980, 700)

        # MVC
        self.model = CatalogModel(self)
        self.controller = CatalogController(self.model, self)

        # Donate URL detection
        self.donate_url, self.donate_tooltip = self._detect_donate_url()
        self.current_github_url = config.SOCIAL_CONFIG["github"]["link"]

        # Build UI
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self._setup_sidebar()
        self._setup_content_area()

        # Donate animation
        self.app_manager = self.controller.app_manager
        self.app_manager.save_donate_link_preference(self.donate_url)
        self.animator = DonateAnimator(self.btn_donate)
        self.animator.start()

        # Connect model signals to view slots
        self._connect_model_signals()

        QTimer.singleShot(100, self.controller.load_catalog)
        QTimer.singleShot(200, self.load_icons)

    def _detect_donate_url(self) -> tuple[str, str]:
        sys_locale = QLocale.system()
        is_cis_locale = (
            sys_locale.language() in [QLocale.Ukrainian, QLocale.Russian]
        ) or (
            sys_locale.country() in [QLocale.Ukraine, QLocale.Russia, QLocale.Belarus]
        )

        tz_id = QTimeZone.systemTimeZoneId().data().decode("utf-8", errors="ignore")
        tz_markers = ["Kiev", "Kyiv", "Ukraine", "Moscow", "Minsk", "FLE", "GTB"]
        is_cis_timezone = any(marker in tz_id for marker in tz_markers)

        donate_cfg = config.SOCIAL_CONFIG["donate"]

        if is_cis_locale or is_cis_timezone:
            self.console.log("UA/CIS -> Donatik")
            return donate_cfg["link_ua"], "Підтримати розробку"
        else:
            self.console.log("Global -> Patreon")
            return donate_cfg["link_global"], "Support Development"

    def _setup_sidebar(self):
        container = QWidget()
        container.setObjectName("Sidebar")
        container.setFixedWidth(300)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 20, 10, 10)

        header = QLabel("AVAILABLE APPS")
        header.setObjectName("SidebarHeader")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        self.apps_list = QListWidget()
        self.apps_list.setIconSize(QSize(32, 32))
        self.apps_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.apps_list.currentItemChanged.connect(self._on_app_selected)
        layout.addWidget(self.apps_list)

        self.refresh_btn = QPushButton("↻ Refresh Catalog")
        self.refresh_btn.setObjectName("RefreshBtn")
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.controller.force_refresh_catalog)
        layout.addWidget(self.refresh_btn)

        self.main_layout.addWidget(container)

    def _setup_content_area(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(15)

        top_bar = self._setup_top_bar()
        layout.addLayout(top_bar)

        self.app_title = QLabel("Select an Application")
        self.app_title.setObjectName("AppTitle")
        self.app_title.setWordWrap(True)
        self.app_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.app_title)

        self.app_desc = QLabel("Choose an application from the list.")
        self.app_desc.setObjectName("AppDescription")
        self.app_desc.setWordWrap(True)
        self.app_desc.setAlignment(Qt.AlignTop)
        layout.addWidget(self.app_desc)

        self.changes_label = QLabel("WHAT'S NEW")
        self.changes_label.setObjectName("ChangesHeader")
        self.changes_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.changes_label)

        self.changelog_viewer = QTextBrowser()
        self.changelog_viewer.setObjectName("ChangelogViewer")
        self.changelog_viewer.setOpenExternalLinks(True)
        layout.addWidget(self.changelog_viewer)

        action_area = self._setup_action_area()
        layout.addLayout(action_area)

        self.main_layout.addWidget(container)

    def _setup_top_bar(self) -> QHBoxLayout:
        top_bar = QHBoxLayout()

        # Telegram
        self.btn_telegram = QPushButton()
        self.btn_telegram.setObjectName("SocialButton")
        self.btn_telegram.setToolTip("Join Telegram Channel")
        self.btn_telegram.setCursor(Qt.PointingHandCursor)
        self.btn_telegram.setFixedSize(32, 32)
        tg_url = config.SOCIAL_CONFIG["telegram"]["link"]
        self.btn_telegram.clicked.connect(lambda: webbrowser.open(tg_url))
        top_bar.addWidget(self.btn_telegram)

        # Donate
        self.btn_donate = AnimatedIconButton()
        self.btn_donate.setObjectName("SocialButton")
        self.btn_donate.setToolTip(self.donate_tooltip)
        self.btn_donate.setCursor(Qt.PointingHandCursor)
        self.btn_donate.setFixedSize(32, 32)
        self.btn_donate.clicked.connect(lambda: webbrowser.open(self.donate_url))
        top_bar.addWidget(self.btn_donate)

        # GitHub
        self.btn_github = QPushButton()
        self.btn_github.setObjectName("SocialButton")
        self.btn_github.setToolTip("Open Source Repository")
        self.btn_github.setCursor(Qt.PointingHandCursor)
        self.btn_github.setFixedSize(32, 32)
        self.btn_github.clicked.connect(self._open_github)
        top_bar.addWidget(self.btn_github)

        top_bar.addStretch()

        # Core update button
        self.core_update_btn = QPushButton("Update Core ⬇")
        self.core_update_btn.setObjectName("CoreUpdateBtn")
        self.core_update_btn.setCursor(Qt.PointingHandCursor)
        self.core_update_btn.setVisible(False)
        self.core_update_btn.clicked.connect(self._on_core_update_clicked)
        top_bar.addWidget(self.core_update_btn)

        # Version labels
        version_container = QWidget()
        version_layout = QVBoxLayout(version_container)
        version_layout.setContentsMargins(10, 0, 0, 0)
        version_layout.setSpacing(2)

        self.core_version_label = QLabel("Core: Checking...")
        self.core_version_label.setObjectName("CoreVersionLabel")
        self.core_version_label.setAlignment(Qt.AlignRight)
        version_layout.addWidget(self.core_version_label)

        self.app_version_label = QLabel("App: -")
        self.app_version_label.setObjectName("AppVersionLabel")
        self.app_version_label.setAlignment(Qt.AlignRight)
        version_layout.addWidget(self.app_version_label)

        top_bar.addWidget(version_container)
        return top_bar

    def _setup_action_area(self) -> QHBoxLayout:
        action_area = QHBoxLayout()

        self.status_label = QLabel("")
        self.status_label.setObjectName("StatusLabel")
        action_area.addWidget(self.status_label)
        action_area.addStretch()

        self.update_btn = QPushButton("Update")
        self.update_btn.setObjectName("UpdateBtn")
        self.update_btn.setFixedSize(120, 50)
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.setVisible(False)
        self.update_btn.clicked.connect(self.controller.start_installation)
        action_area.addWidget(self.update_btn)
        action_area.addSpacing(10)

        self.action_btn = SmartButton()
        self.action_btn.clicked.connect(self._on_action_clicked)
        action_area.addWidget(self.action_btn)

        return action_area

    def _connect_model_signals(self):
        self.model.catalog_loaded.connect(self._on_catalog_loaded)
        self.model.app_selected.connect(self._on_app_data_selected)
        self.model.core_version_updated.connect(self._on_core_version_updated)
        self.model.core_update_available.connect(self._on_core_update_available)
        self.model.status_changed.connect(self._on_status_changed)
        self.model.error_occurred.connect(self._on_model_error)

    @Slot(list)
    def _on_catalog_loaded(self, apps: list[AppData]):
        self.apps_list.clear()
        for app in apps:
            item = QListWidgetItem(app.name)
            item.setIcon(app.icon)
            item.setData(Qt.UserRole, app)
            self.apps_list.addItem(item)

        if self.apps_list.count() > 0:
            self.apps_list.setCurrentRow(0)

        launcher_update = self.app_manager.get_launcher_update_info()
        if launcher_update:
            new_ver = launcher_update.get("pending_update_version")
            self.console.log(f"Launcher update found: {new_ver}")

            reply = QMessageBox.question(
                self,
                "Launcher Update Available",
                f"A new version of Launcher (v{new_ver}) is available.\nUpdate and restart now?",
                QMessageBox.Yes | QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                self._set_ui_interactivity(False)
                self.app_manager.update_launcher(launcher_update)
                return

        QTimer.singleShot(500, self._check_launcher_nag)

    @Slot(AppData)
    def _on_app_data_selected(self, app: AppData):
        if app.repo_url:
            self.current_github_url = app.repo_url
            self.btn_github.setToolTip(f"Open Repository: {app.name}")
            self.btn_github.setEnabled(True)
            self.btn_github.setProperty("has_link", True)
        else:
            self.current_github_url = config.SOCIAL_CONFIG["github"]["link"]
            self.btn_github.setToolTip("Open Launcher Repository")

        self.console.log(f"Selected: {app.name}")

        self.app_title.setText(app.name)
        self.app_desc.setText(app.description or "No description provided.")

        if not app.is_local:
            ver_text = f"App: v{app.latest_version} (Available)"
            self.app_version_label.setProperty("state", "not_installed")
        elif app.update_available:
            ver_text = f"App: v{app.local_version} ➜ v{app.latest_version}"
            self.app_version_label.setProperty("state", "update")
        else:
            ver_text = f"App: v{app.local_version}"
            self.app_version_label.setProperty("state", "normal")

        self.app_version_label.setText(ver_text)
        self.app_version_label.style().unpolish(self.app_version_label)
        self.app_version_label.style().polish(self.app_version_label)

        if app.changelog:
            self.changelog_viewer.setMarkdown(app.changelog)
        else:
            self.changelog_viewer.setMarkdown("*No release notes available.*")

        self._refresh_button_state()

    @Slot(str)
    def _on_core_version_updated(self, version: str):
        self.core_version_label.setText(f"Core: {version}")

    @Slot(object)
    def _on_core_update_available(self, update_info):
        self.core_update_btn.setVisible(True)
        self.core_version_label.setProperty("has_update", True)
        self.core_version_label.style().unpolish(self.core_version_label)
        self.core_version_label.style().polish(self.core_version_label)
        self.core_version_label.setText(
            f"Core: {update_info.local_version} → {update_info.remote_version}"
        )
        self.core_update_btn.setToolTip(update_info.changelog)
        self.console.log("Core update available displayed.")

    @Slot(str, str)
    def _on_status_changed(self, message: str, style: str):
        self.console.print(message, style=style)
        self.status_label.setText(message)

    @Slot(str)
    def _on_model_error(self, message: str):
        QMessageBox.critical(self, "Error", f"An error occurred:\n\n{message}")
        self._set_ui_interactivity(True)
        self._refresh_button_state()

    @Slot()
    def _on_app_selected(self, current, previous):
        if not current:
            return
        app = current.data(Qt.UserRole)
        if isinstance(app, AppData):
            self.controller.select_app(app)

    @Slot()
    def _on_action_clicked(self):
        app = self.model.selected_app
        if not app:
            return

        state = self.action_btn._current_state
        self.console.log(f"Main action button clicked. State: {state}")

        if state == SmartButton.STATE_NOT_INSTALLED:
            self.controller.start_installation()
        elif state == SmartButton.STATE_INSTALLED:
            self._handle_launch_with_critical_check(app)

    def _handle_launch_with_critical_check(self, app: AppData):
        if app.is_critical and app.update_available:
            dlg = CriticalUpdateDialog(self, app.name, app.local_version, app.latest_version)
            dlg.exec()

            action = dlg.result_action
            if action == "cancel":
                self.console.log("Launch cancelled by user (Critical Update Dialog).")
                return
            elif action == "update":
                self.console.log("User chose to update from critical dialog.")
                self.controller.start_installation()
                return
            elif action == "launch":
                self.console.log("User chose 'Launch Anyway'. Proceeding with risk.")

        self.controller.start_launch_sequence(app.folder_name)

    @Slot()
    def _on_core_update_clicked(self):
        self.console.log("Core update button clicked.")
        self._set_ui_interactivity(False)
        self.core_update_btn.setEnabled(False)
        self.core_update_btn.setText("Updating...")
        self.controller.update_core()

    def _refresh_button_state(self):
        app = self.model.selected_app

        if not app:
            self.action_btn.update_state(SmartButton.STATE_NO_SELECTION)
            self.update_btn.setVisible(False)
            return

        self.update_btn.setVisible(app.is_local and app.update_available)

        if app.update_available:
            self.update_btn.setProperty("critical", app.is_critical)
            self.update_btn.style().unpolish(self.update_btn)
            self.update_btn.style().polish(self.update_btn)

        if app.is_local:
            self.action_btn.update_state(SmartButton.STATE_INSTALLED)
            self.action_btn.setProperty("critical", app.update_available and app.is_critical)
            self.action_btn.style().unpolish(self.action_btn)
            self.action_btn.style().polish(self.action_btn)

            if app.update_available and app.is_critical:
                self.action_btn.setText("LAUNCH (RISK)")
        else:
            self.action_btn.update_state(SmartButton.STATE_NOT_INSTALLED)

    def _check_launcher_nag(self):
        show, count = self.app_manager.register_launch_and_check_nag(
            "launcher", is_launcher=True
        )
        if show:
            self.console.log(f"Showing launcher donation dialog (Count: {count})")
            dlg = DonationDialog(self, "Omni Trans Launcher", count, self.donate_url)
            dlg.exec()

    def _set_ui_interactivity(self, enabled: bool):
        self.apps_list.setEnabled(enabled)
        self.refresh_btn.setEnabled(enabled)
        self.core_update_btn.setEnabled(enabled)

    @Slot()
    def _open_github(self):
        webbrowser.open(self.current_github_url)

    def load_icons(self):
        """Load social icons."""
        for name, btn in [
            ("telegram", self.btn_telegram),
            ("donate", self.btn_donate),
            ("github", self.btn_github),
        ]:
            icon = IconManager.get_qicon(name)
            if not icon.isNull():
                btn.setIcon(icon)
                btn.setIconSize(QSize(24, 24))
