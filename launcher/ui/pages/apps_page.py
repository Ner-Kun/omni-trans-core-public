import webbrowser

from PySide6.QtCore import QSize, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    FluentIcon,
    IndeterminateProgressBar,
    InfoBadge,
    InfoLevel,
    ListWidget,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    SmoothScrollArea,
    SubtitleLabel,
    TitleLabel,
    TransparentToolButton,
    setCustomStyleSheet,
)

from launcher import config
from launcher.controllers.catalog_controller import CatalogController
from launcher.models.app_model import AppData
from launcher.models.catalog_model import CatalogModel
from launcher.ui.dialogs import CriticalUpdateDialog
from launcher.ui.widgets import AppListItem
from launcher.utils.changelog import clean_changelog
from launcher.utils.heartbeat import HeartbeatAnimator
from launcher.utils.icon_manager import IconManager

GREEN_ACTION_QSS = """
PrimaryPushButton {
    background-color: #4ec990;
    border: 1px solid #4ec990;
    color: #ffffff;
}
PrimaryPushButton:hover {
    background-color: #3db07a;
    border-color: #3db07a;
}
PrimaryPushButton:pressed {
    background-color: #2d9060;
    border-color: #2d9060;
}
PrimaryPushButton:disabled {
    background-color: #2a2a2e;
    border-color: #2e2e32;
    color: #505050;
}
"""

RED_ACTION_QSS = """
PrimaryPushButton {
    background-color: #e85555;
    border: 1px solid #e85555;
    color: #ffffff;
}
PrimaryPushButton:hover {
    background-color: #cc4040;
    border-color: #cc4040;
}
PrimaryPushButton:pressed {
    background-color: #b03030;
    border-color: #b03030;
}
PrimaryPushButton:disabled {
    background-color: #2a2a2e;
    border-color: #2e2e32;
    color: #505050;
}
"""

RED_PUSH_QSS = """
PushButton {
    background-color: #e85555;
    border: 1px solid #e85555;
    color: #ffffff;
}
PushButton:hover {
    background-color: #cc4040;
    border-color: #cc4040;
}
PushButton:pressed {
    background-color: #b03030;
    border-color: #b03030;
}
PushButton:disabled {
    background-color: #2a2a2e;
    border-color: #2e2e32;
    color: #505050;
}
"""


class AppDetailWidget(QWidget):
    action_clicked = Signal()
    update_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._app: AppData | None = None
        self._busy = False
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.scroll = SmoothScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll.setStyleSheet(
            "SmoothScrollArea { background: transparent; border: none; }"
        )
        self.scroll.viewport().setStyleSheet("background: transparent;")
        outer.addWidget(self.scroll)

        container = QWidget()
        self.scroll.setWidget(container)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)

        card = CardWidget(container)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(16)

        self.icon_label = QLabel(card)
        self.icon_label.setFixedSize(64, 64)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.icon_label)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        self.title_label = SubtitleLabel("Select an application", card)
        self.title_label.setWordWrap(True)
        title_layout.addWidget(self.title_label)

        version_row = QHBoxLayout()
        version_row.setSpacing(8)
        self.version_label = CaptionLabel("", card)
        self.state_badge = InfoBadge.info("", card)
        self.state_badge.setVisible(False)
        version_row.addWidget(self.version_label)
        version_row.addWidget(self.state_badge)
        version_row.addStretch()
        title_layout.addLayout(version_row)
        header.addLayout(title_layout, 1)

        card_layout.addLayout(header)

        self.description_label = BodyLabel("", card)
        self.description_label.setWordWrap(True)
        card_layout.addWidget(self.description_label)

        self.status_label = CaptionLabel("", card)
        self.status_label.setWordWrap(True)
        card_layout.addWidget(self.status_label)

        action_row = QHBoxLayout()
        action_row.addStretch()

        self.update_btn = PushButton("Update", card)
        self.update_btn.setVisible(False)
        self.update_btn.setMinimumWidth(110)
        self.update_btn.clicked.connect(self.update_clicked.emit)
        action_row.addWidget(self.update_btn)

        self.action_btn = PrimaryPushButton("Install", card)
        self.action_btn.setMinimumWidth(130)
        self.action_btn.clicked.connect(self.action_clicked.emit)
        action_row.addWidget(self.action_btn)

        card_layout.addLayout(action_row)

        self.progress = IndeterminateProgressBar(card)
        self.progress.setVisible(False)
        card_layout.addWidget(self.progress)

        card_layout.addWidget(SubtitleLabel("What's new", card))

        self.changelog_note = CaptionLabel("", card)
        self.changelog_note.setWordWrap(True)
        self.changelog_note.setVisible(False)
        card_layout.addWidget(self.changelog_note)

        self.changelog = QLabel(card)
        self.changelog.setTextFormat(Qt.TextFormat.MarkdownText)
        self.changelog.setWordWrap(True)
        self.changelog.setOpenExternalLinks(True)
        self.changelog.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        self.changelog.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.changelog.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self.changelog.setContentsMargins(0, 0, 0, 0)
        self.changelog.setIndent(0)
        self.changelog.setStyleSheet("background: transparent;")
        card_layout.addWidget(self.changelog)

        container_layout.addWidget(card, 1)
        self.set_app(None)

    def set_app(self, app: AppData | None) -> None:
        self._app = app

        if app is None:
            self.icon_label.clear()
            self.title_label.setText("Select an application")
            self.version_label.setText("")
            self.state_badge.setVisible(False)
            self.description_label.setText(
                "Choose an app from the list to see its details."
            )
            self.changelog_note.setVisible(False)
            self.changelog.setText("")
            self.action_btn.setText("Install")
            self.action_btn.setEnabled(False)
            self.update_btn.setVisible(False)
            self._apply_action_style(None)
            self._apply_update_style(None)
            self._refresh_status()
            return

        icon = app.icon if not app.icon.isNull() else FluentIcon.APPLICATION.icon()
        self.icon_label.setPixmap(icon.pixmap(QSize(64, 64)))
        self.title_label.setText(app.name)

        if not app.is_local:
            version = f"Available: v{app.latest_version}"
        elif app.update_available:
            version = f"Installed: v{app.local_version}  →  v{app.latest_version}"
        else:
            version = f"Installed: v{app.local_version}"
        self.version_label.setText(version)

        self._update_state_badge(app)
        self.description_label.setText(app.description or "No description provided.")

        body, note = clean_changelog(app.changelog)
        self.changelog_note.setText(note or "")
        self.changelog_note.setVisible(bool(note))
        self.changelog.setText(body or "*No release notes available.*")
        self.changelog.updateGeometry()

        self.update_btn.setVisible(app.is_local and app.update_available)
        self.update_btn.setEnabled(
            not app.is_running and not app.is_launching and not self._busy
        )
        if app.is_running:
            self.update_btn.setToolTip("Close the application before updating.")
        elif app.is_launching:
            self.update_btn.setToolTip("Wait until the application starts.")
        else:
            self.update_btn.setToolTip("")

        if app.is_running:
            self.action_btn.setText("Running")
        elif app.is_launching:
            self.action_btn.setText("Launching...")
        elif not app.is_local:
            self.action_btn.setText("Install")
        elif app.is_critical and app.update_available:
            self.action_btn.setText("Launch (risk)")
        else:
            self.action_btn.setText("Launch")

        self.action_btn.setEnabled(
            not app.is_running and not app.is_launching and not self._busy
        )
        self._apply_action_style(app)
        self._apply_update_style(app)
        self._refresh_status()

    def set_busy(self, busy: bool, message: str = "") -> None:
        self._busy = busy
        self.action_btn.setEnabled(
            not busy
            and self._app is not None
            and not self._app.is_running
            and not self._app.is_launching
        )
        self.update_btn.setEnabled(
            not busy
            and self._app is not None
            and not self._app.is_running
            and not self._app.is_launching
        )
        self.progress.setVisible(busy)

        if busy:
            self.progress.start()
            self.status_label.setText(message)
            self.status_label.setStyleSheet("")
        else:
            self.progress.stop()
            self._refresh_status()

    def _update_state_badge(self, app: AppData) -> None:
        if app.is_running:
            level, text = InfoLevel.SUCCESS, "Running"
        elif app.is_launching:
            level, text = InfoLevel.INFOAMTION, "Launching"
        elif app.is_critical and app.update_available:
            level, text = InfoLevel.ERROR, "Critical"
        elif app.update_available:
            level, text = InfoLevel.WARNING, "Update"
        elif app.is_local:
            level, text = InfoLevel.SUCCESS, "Installed"
        else:
            level, text = InfoLevel.INFOAMTION, "Available"

        self.state_badge.setLevel(level)
        self.state_badge.setText(text)
        self.state_badge.setVisible(True)

    def _apply_action_style(self, app: AppData | None) -> None:
        if (
            app is None
            or app.is_running
            or app.is_launching
            or not app.is_local
        ):
            qss = ""
        elif app.is_critical and app.update_available:
            qss = RED_ACTION_QSS
        else:
            qss = GREEN_ACTION_QSS

        setCustomStyleSheet(self.action_btn, qss, qss)

    def _apply_update_style(self, app: AppData | None) -> None:
        if (
            app is not None
            and app.is_critical
            and app.update_available
            and not app.is_launching
        ):
            self.update_btn.setText("Update now")
            qss = RED_PUSH_QSS
        else:
            self.update_btn.setText("Update")
            qss = ""

        setCustomStyleSheet(self.update_btn, qss, qss)

    def _refresh_status(self) -> None:
        if self._app is None:
            self.status_label.setText("")
            self.status_label.setStyleSheet("")
        elif self._app.is_running:
            self.status_label.setText("The application is already running.")
            self.status_label.setStyleSheet("")
        elif self._app.is_launching:
            self.status_label.setText("")
            self.status_label.setStyleSheet("")
        elif self._app.is_critical and self._app.update_available:
            self.status_label.setText(
                "Critical update available. Update before launching."
            )
            self.status_label.setStyleSheet("color: #e85555;")
        else:
            self.status_label.setText("")
            self.status_label.setStyleSheet("")


class AppsPage(QWidget):
    def __init__(
        self,
        model: CatalogModel,
        controller: CatalogController,
        donate_url: str,
        donate_tooltip: str,
        remembered_app: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("appsPage")
        self.model = model
        self.controller = controller
        self.donate_url = donate_url
        self.donate_tooltip = donate_tooltip
        self._selected_app: AppData | None = None
        self._busy = False
        self._current_repo_url = config.SOCIAL_CONFIG["github"]["link"]
        self._item_widgets: dict[str, AppListItem] = {}
        self._remembered_app = remembered_app

        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)

        header = QHBoxLayout()
        header.setSpacing(8)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)
        title_layout.addWidget(TitleLabel("Applications", self))
        title_layout.addWidget(
            CaptionLabel("Install, update and launch Omni apps", self)
        )
        header.addLayout(title_layout)
        header.addStretch()

        self.core_label = CaptionLabel("Core: ...", self)
        header.addWidget(self.core_label)

        self.core_update_btn = PrimaryPushButton("Update core", self)
        self.core_update_btn.setVisible(False)
        header.addWidget(self.core_update_btn)

        self.refresh_btn = TransparentToolButton(self)
        self.refresh_btn.setIcon(FluentIcon.SYNC.icon())
        self.refresh_btn.setIconSize(QSize(18, 18))
        self.refresh_btn.setToolTip("Refresh catalog")
        header.addWidget(self.refresh_btn)

        self.telegram_btn = TransparentToolButton(self)
        telegram_icon = IconManager.get_qicon("telegram")
        if not telegram_icon.isNull():
            self.telegram_btn.setIcon(telegram_icon)
        self.telegram_btn.setIconSize(QSize(18, 18))
        self.telegram_btn.setToolTip("Telegram")
        header.addWidget(self.telegram_btn)

        self.donate_btn = TransparentToolButton(self)
        donate_icon = IconManager.get_qicon("donate")
        self.donate_btn.setIcon(
            donate_icon if not donate_icon.isNull() else FluentIcon.HEART.icon()
        )
        self.donate_btn.setIconSize(QSize(18, 18))
        self.donate_btn.setToolTip(self.donate_tooltip)
        header.addWidget(self.donate_btn)

        self.github_btn = TransparentToolButton(self)
        self.github_btn.setIcon(FluentIcon.GITHUB.icon())
        self.github_btn.setIconSize(QSize(18, 18))
        self.github_btn.setToolTip("GitHub")
        header.addWidget(self.github_btn)

        layout.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(20)

        self.app_list = ListWidget(self)
        self.app_list.setFixedWidth(340)
        self.app_list.setIconSize(QSize(32, 32))
        self.app_list.setSpacing(4)
        self.app_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        body.addWidget(self.app_list)

        self.detail = AppDetailWidget(self)
        body.addWidget(self.detail, 1)

        layout.addLayout(body, 1)

        self.page_status = CaptionLabel("", self)
        layout.addWidget(self.page_status)

        self.donate_animator = HeartbeatAnimator(
            self.donate_btn,
            QSize(18, 18),
            QSize(22, 22),
            4000,
            self,
        )
        self.donate_animator.start()

    def _connect_signals(self) -> None:
        self.app_list.currentItemChanged.connect(self._on_app_selected)
        self.refresh_btn.clicked.connect(self.controller.force_refresh_catalog)
        self.core_update_btn.clicked.connect(self.controller.update_core)
        self.detail.action_clicked.connect(self._on_action_clicked)
        self.detail.update_clicked.connect(self.controller.start_installation)

        self.telegram_btn.clicked.connect(
            lambda: webbrowser.open(config.SOCIAL_CONFIG["telegram"]["link"])
        )
        self.donate_btn.clicked.connect(lambda: webbrowser.open(self.donate_url))
        self.github_btn.clicked.connect(self._open_github)

        self.model.catalog_loaded.connect(self._on_catalog_loaded)
        self.model.app_selected.connect(self._on_app_data_selected)
        self.model.app_state_changed.connect(self._on_app_state_changed)
        self.model.core_version_updated.connect(self._on_core_version_updated)
        self.model.core_update_available.connect(self._on_core_update_available)
        self.model.status_changed.connect(self._on_status_changed)
        self.model.error_occurred.connect(self._on_error)
        self.controller.busy_changed.connect(self._on_busy_changed)

    @Slot(list)
    def _on_catalog_loaded(self, apps: list[AppData]) -> None:
        current_folder = (
            self._selected_app.folder_name
            if self._selected_app
            else self._remembered_app
        )
        self._remembered_app = ""

        self.app_list.clear()
        self._item_widgets.clear()
        selected_item = None

        for app in apps:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, app)
            item.setSizeHint(QSize(0, 64))
            self.app_list.addItem(item)

            widget = AppListItem(app, self.app_list)
            self.app_list.setItemWidget(item, widget)
            self._item_widgets[app.folder_name] = widget

            if current_folder and app.folder_name == current_folder:
                selected_item = item

        if selected_item is None and self.app_list.count() > 0:
            selected_item = self.app_list.item(0)

        if selected_item is not None:
            self.app_list.setCurrentItem(selected_item)
        else:
            self._selected_app = None
            self.detail.set_app(None)

    @Slot(object, object)
    def _on_app_selected(self, current, _previous) -> None:
        if current is None:
            return
        app = current.data(Qt.ItemDataRole.UserRole)
        if isinstance(app, AppData):
            self.controller.select_app(app)

    @Slot(AppData)
    def _on_app_data_selected(self, app: AppData) -> None:
        self._selected_app = app
        self.detail.set_app(app)

        if app.repo_url:
            self._current_repo_url = app.repo_url
            self.github_btn.setToolTip(f"Open repository: {app.name}")
        else:
            self._current_repo_url = config.SOCIAL_CONFIG["github"]["link"]
            self.github_btn.setToolTip("GitHub")

    @Slot(AppData)
    def _on_app_state_changed(self, app: AppData) -> None:
        widget = self._item_widgets.get(app.folder_name)
        if widget is not None:
            widget.update_state(app)

        if (
            self._selected_app is not None
            and self._selected_app.folder_name == app.folder_name
        ):
            self._selected_app = app
            self.detail.set_app(app)

    @Slot()
    def _on_action_clicked(self) -> None:
        app = self._selected_app
        if not app or self._busy or app.is_running or app.is_launching:
            return

        if not app.is_local:
            self.controller.start_installation()
            return

        if app.is_critical and app.update_available:
            dialog = CriticalUpdateDialog(
                self,
                app.name,
                app.local_version,
                app.latest_version,
            )
            dialog.exec()
            if dialog.result_action == "update":
                self.controller.start_installation()
                return
            if dialog.result_action == "cancel":
                return

        self.controller.start_launch_sequence(app.folder_name)

    @Slot(bool, str)
    def _on_busy_changed(self, busy: bool, message: str) -> None:
        self._busy = busy
        self.app_list.setEnabled(not busy)
        self.refresh_btn.setEnabled(not busy)
        self.core_update_btn.setEnabled(not busy)
        self.detail.set_busy(busy, message)

    @Slot(str, str)
    def _on_status_changed(self, message: str, _style: str) -> None:
        self.page_status.setText(message)

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self.page_status.setText("")
        box = MessageBox("Error", message, self)
        box.hideCancelButton()
        box.yesButton.setText("OK")
        box.exec()

    @Slot(str)
    def _on_core_version_updated(self, version: str) -> None:
        self.core_label.setText(f"Core: {version}")
        self.core_update_btn.setVisible(False)

    @Slot(object)
    def _on_core_update_available(self, update_info) -> None:
        self.core_update_btn.setVisible(True)
        self.core_update_btn.setToolTip(
            update_info.changelog or "Core update available"
        )

    @Slot()
    def _open_github(self) -> None:
        webbrowser.open(self._current_repo_url)

    def stop_animations(self) -> None:
        self.donate_animator.stop()
