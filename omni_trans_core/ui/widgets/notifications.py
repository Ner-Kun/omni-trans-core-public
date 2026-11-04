import logging
from typing import Callable, Optional

from PySide6 import QtCore, QtWidgets
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
    Dialog,
    FluentIcon,
    ListWidget,
    MessageBox,
    PushButton,
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

FILTER_KEYS = (
    "notification.center.filter_all",
    "notification.center.filter_info",
    "notification.center.filter_success",
    "notification.center.filter_warning",
    "notification.center.filter_error",
)


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
        self._notification_center: Optional["NotificationCenter"] = None
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

        if self._notification_center is None:
            self._notification_center = NotificationCenter(
                self.manager, self.window()
            )
        self._notification_center.show()
        self._notification_center.raise_()
        self._notification_center.activateWindow()

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


@auto_register(
    ("", "windowTitle", "notification.center.title"),
    ("clear_all_btn", "text", "notification.center.clear_all"),
    ("no_notifications_label", "text", "notification.center.no_notifications"),
)
class NotificationCenter(Dialog):
    def __init__(self, manager: "NotificationManager", parent=None):
        self.manager = manager
        super().__init__("Notifications", "", parent)
        self.setFixedSize(460, 560)
        self.contentLabel.hide()
        self.buttonGroup.hide()
        self._build_ui()
        self._connect_signals()
        self._populate_list()
        self._update_empty_state()

    def _build_ui(self):
        self.filter_combo = ComboBox(self)
        self._refresh_filter_items()
        self.vBoxLayout.insertWidget(1, self.filter_combo)

        self.notifications_list = ListWidget(self)
        self.vBoxLayout.insertWidget(2, self.notifications_list, 1)

        self.no_notifications_label = BodyLabel(self)
        self.no_notifications_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignCenter
        )
        self.vBoxLayout.insertWidget(3, self.no_notifications_label)

        self.clear_all_btn = PushButton(self)
        self.vBoxLayout.insertWidget(4, self.clear_all_btn)

    def _refresh_filter_items(self):
        current = self.filter_combo.currentIndex()
        self.filter_combo.blockSignals(True)
        self.filter_combo.clear()
        for key in FILTER_KEYS:
            self.filter_combo.addItem(translate(key))
        if 0 <= current < self.filter_combo.count():
            self.filter_combo.setCurrentIndex(current)
        self.filter_combo.blockSignals(False)

    def _connect_signals(self):
        self.filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.clear_all_btn.clicked.connect(self._on_clear_all)
        self.manager.notification_added.connect(self._on_notification_added)
        self.manager.notification_removed.connect(self._on_notification_removed)
        self.manager.history_cleared.connect(self._on_history_cleared)
        loc_man.language_changed.connect(self._refresh_filter_items)

    def _populate_list(self):
        self.notifications_list.clear()
        filter_type = self._get_current_filter()
        for notif in self.manager.get_history():
            if filter_type and notif.type != filter_type:
                continue
            self._add_notification_item(notif)
        self._update_empty_state()

    def _get_current_filter(self) -> Optional[NotificationType]:
        index = self.filter_combo.currentIndex()
        types = [
            None,
            NotificationType.INFO,
            NotificationType.SUCCESS,
            NotificationType.WARNING,
            NotificationType.ERROR,
        ]
        return types[index] if 0 <= index < len(types) else None

    def _add_notification_item(self, notif: NotificationItem):
        style_config = NOTIFICATION_STYLES.get(notif.type, {})
        icon = style_config.get("icon", "ℹ️")
        time_ago = self._format_time_ago(notif.timestamp)

        item_widget = QtWidgets.QWidget()
        item_layout = QtWidgets.QVBoxLayout(item_widget)
        item_layout.setContentsMargins(8, 6, 8, 6)
        item_layout.setSpacing(4)

        top_layout = QtWidgets.QHBoxLayout()
        icon_label = BodyLabel(icon, item_widget)
        top_layout.addWidget(icon_label)
        text_label = BodyLabel(notif.text, item_widget)
        text_label.setWordWrap(True)
        top_layout.addWidget(text_label, stretch=1)
        item_layout.addLayout(top_layout)

        bottom_layout = QtWidgets.QHBoxLayout()
        bottom_layout.setContentsMargins(24, 0, 0, 0)
        bottom_layout.addWidget(CaptionLabel(time_ago, item_widget))
        bottom_layout.addStretch()
        delete_btn = TransparentToolButton(FluentIcon.DELETE, item_widget)
        delete_btn.clicked.connect(
            lambda _=False, nid=notif.id: self._on_delete_notification(nid)
        )
        bottom_layout.addWidget(delete_btn)
        item_layout.addLayout(bottom_layout)

        list_item = QtWidgets.QListWidgetItem(self.notifications_list)
        list_item.setSizeHint(item_widget.sizeHint())
        self.notifications_list.addItem(list_item)
        self.notifications_list.setItemWidget(list_item, item_widget)

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

    def _update_empty_state(self):
        has_items = self.notifications_list.count() > 0
        self.no_notifications_label.setVisible(not has_items)
        self.notifications_list.setVisible(has_items)

    def _on_filter_changed(self, _index: int):
        self._populate_list()

    def _on_clear_all(self):
        box = MessageBox(
            translate("notification.center.clear_all_confirm_title"),
            translate("notification.center.clear_all_confirm_text"),
            self,
        )
        box.yesButton.setText(translate("notification.center.clear_all"))
        box.cancelButton.setText("Cancel")
        if box.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.manager.clear_history()

    def _on_delete_notification(self, notification_id: str):
        self.manager.remove_notification(notification_id)
        self._populate_list()

    def _on_notification_added(self, _notification: NotificationItem):
        self._populate_list()

    def _on_notification_removed(self, _notification_id: str):
        self._populate_list()

    def _on_history_cleared(self):
        self._populate_list()

    def showEvent(self, event):
        super().showEvent(event)
        self.manager.mark_all_as_read()
        self._populate_list()
