import logging
from typing import Optional

from PySide6 import QtCore, QtWidgets
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    Flyout,
    FlyoutAnimationType,
    FlyoutViewBase,
    PushButton,
    StrongBodyLabel,
    TransparentToolButton,
)

from ... import settings
from ...localization_manager import auto_register, loc_man, translate
from ...notification_manager import (
    NOTIFICATION_STYLES,
    NotificationItem,
    NotificationManager,
    NotificationType,
)

logger = logging.getLogger("CORE_UI.widgets")

PANEL_WIDTH = 400
MESSAGE_WIDTH = 286
MAX_LIST_HEIGHT = 380

SCROLL_AREA_STYLE = """
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { width: 8px; background: transparent; }
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 40);
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


@auto_register(
    ("", "toolTip", "notification.bell.tooltip"),
)
class NotificationBell(TransparentToolButton):
    bell_clicked = QtCore.Signal()

    def __init__(self, manager: "NotificationManager", parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setIcon(FluentIcon.RINGER)
        self.setFixedSize(36, 32)
        self._flyout: Optional[Flyout] = None
        self._click_count = 0
        self._click_timer = QtCore.QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._reset_click_count)
        self._test_type_index = 0
        self._test_types = [
            NotificationType.INFO,
            NotificationType.SUCCESS,
            NotificationType.WARNING,
            NotificationType.ERROR,
        ]

        self._unread_badge = QtWidgets.QLabel(self)
        self._unread_badge.setMinimumSize(16, 16)
        self._unread_badge.setMaximumSize(16, 16)
        self._unread_badge.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._unread_badge.setStyleSheet(
            "QLabel { background-color: #ff5555; color: white; "
            "border-radius: 8px; font-size: 10px; font-weight: bold; }"
        )
        self._unread_badge.hide()

        self.clicked.connect(self._on_bell_clicked)
        self.manager.unread_count_changed.connect(self._on_unread_count_changed)
        self._update_display()

    def _update_badge_position(self):
        self._unread_badge.move(self.width() - 18, 2)

    def _on_bell_clicked(self):
        self._click_count += 1
        self._click_timer.start(500)
        if self._click_count >= 3:
            self._click_count = 0
            self._click_timer.stop()
            if settings.DEV_MODE_ENABLED:
                self._show_test_notification()
                return

        if self._flyout is not None:
            self._flyout.close()
            self._flyout = None
            return

        self.manager.mark_all_as_read()
        self.bell_clicked.emit()
        view = NotificationCenterView(self.manager, self.window())
        self._flyout = Flyout.make(
            view,
            self,
            self.window(),
            aniType=FlyoutAnimationType.DROP_DOWN,
        )
        self._flyout.closed.connect(self._on_flyout_closed)

    def _on_flyout_closed(self):
        self._flyout = None

    def _reset_click_count(self):
        self._click_count = 0

    def _show_test_notification(self):
        notif_type = self._test_types[self._test_type_index]
        self._test_type_index = (self._test_type_index + 1) % len(self._test_types)
        type_names = {
            NotificationType.INFO: "Info",
            NotificationType.SUCCESS: "Success",
            NotificationType.WARNING: "Warning",
            NotificationType.ERROR: "Error",
        }
        type_name = type_names.get(notif_type, "Unknown")
        self.manager.show_notification(
            type=notif_type,
            text=f"[DEV TEST] {type_name} notification",
            button_text="Test Action",
            on_click=lambda: logger.debug("%s action clicked", type_name),
        )

    def _on_unread_count_changed(self, _count: int):
        self._update_display()

    def _update_display(self):
        unread_count = self.manager.get_unread_count()
        if unread_count > 0:
            self._unread_badge.show()
            self._unread_badge.setText("99+" if unread_count > 99 else str(unread_count))
            self._unread_badge.adjustSize()
            self._update_badge_position()
        else:
            self._unread_badge.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_badge_position()


class NotificationCenterView(FlyoutViewBase):
    """Notification history shown in a flyout anchored to the bell."""

    def __init__(self, manager: "NotificationManager", parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setFixedWidth(PANEL_WIDTH)

        self.vBoxLayout = QtWidgets.QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(16, 12, 16, 12)
        self.vBoxLayout.setSpacing(8)
        self.vBoxLayout.addLayout(self._build_header())
        self._build_list()

        self.manager.notification_added.connect(self._on_history_changed)
        self.manager.notification_removed.connect(self._on_history_changed)
        self.manager.history_cleared.connect(self._on_history_changed)
        loc_man.language_changed.connect(self.retranslate)

        self._populate()

    def _build_header(self) -> QtWidgets.QHBoxLayout:
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(8)

        self.title_label = StrongBodyLabel(
            translate("notification.center.title"), self
        )
        header.addWidget(self.title_label)
        header.addStretch(1)

        self.clear_all_btn = PushButton(
            translate("notification.center.clear_all"), self
        )
        self.clear_all_btn.clicked.connect(self.manager.clear_history)
        header.addWidget(self.clear_all_btn)
        return header

    def _build_list(self) -> None:
        self.scroll_area = QtWidgets.QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setStyleSheet(SCROLL_AREA_STYLE)

        self.items_container = QtWidgets.QWidget(self.scroll_area)
        self.items_layout = QtWidgets.QVBoxLayout(self.items_container)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(2)
        self.scroll_area.setWidget(self.items_container)
        self.vBoxLayout.addWidget(self.scroll_area, 1)

        self.no_notifications_label = BodyLabel(
            translate("notification.center.no_notifications"), self
        )
        self.no_notifications_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignCenter
        )
        self.vBoxLayout.addWidget(self.no_notifications_label)

    def _populate(self) -> None:
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

        history = self.manager.get_history()
        for notification in history:
            self.items_layout.addWidget(self._create_item(notification))
        self.items_layout.addStretch(1)

        has_items = bool(history)
        self.no_notifications_label.setVisible(not has_items)
        self.scroll_area.setVisible(has_items)
        if has_items:
            height = min(
                MAX_LIST_HEIGHT, self.items_container.sizeHint().height() + 4
            )
            self.scroll_area.setFixedHeight(max(80, height))
        self.adjustSize()

    def _create_item(self, notification: NotificationItem) -> QtWidgets.QWidget:
        style = NOTIFICATION_STYLES.get(notification.type, {})
        icon = style.get("icon", "ℹ️")

        row = QtWidgets.QWidget(self.items_container)
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(8)

        icon_label = BodyLabel(icon, row)
        icon_label.setFixedWidth(20)
        layout.addWidget(icon_label, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        text_column = QtWidgets.QVBoxLayout()
        text_column.setSpacing(0)
        message = BodyLabel(notification.text, row)
        message.setWordWrap(True)
        message.setFixedWidth(MESSAGE_WIDTH)
        text_column.addWidget(message)

        time_ago = CaptionLabel(
            self._format_time_ago(notification.timestamp), row
        )
        text_column.addWidget(time_ago)
        layout.addLayout(text_column, 1)

        delete_btn = TransparentToolButton(FluentIcon.DELETE, row)
        delete_btn.setFixedSize(28, 28)
        delete_btn.clicked.connect(
            lambda _=False, nid=notification.id: self.manager.remove_notification(nid)
        )
        layout.addWidget(delete_btn, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        return row

    def _format_time_ago(self, timestamp: float) -> str:
        now = QtCore.QDateTime.currentSecsSinceEpoch()
        diff = now - timestamp
        if diff < 60:
            return translate("notification.center.time_now")
        if diff < 3600:
            return translate("notification.center.time_minutes", minutes=diff // 60)
        if diff < 86400:
            return translate("notification.center.time_hours", hours=diff // 3600)
        return translate("notification.center.time_days", days=diff // 86400)

    def _on_history_changed(self, *_args) -> None:
        self._populate()

    def retranslate(self) -> None:
        self.title_label.setText(translate("notification.center.title"))
        self.clear_all_btn.setText(translate("notification.center.clear_all"))
        self.no_notifications_label.setText(
            translate("notification.center.no_notifications")
        )
        self._populate()
