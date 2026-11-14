"""Tests for the notification flyout panel."""

from omni_trans_core import settings
from omni_trans_core.notification_manager import (
    NotificationManager,
    NotificationType,
)
from omni_trans_core.ui.widgets.notifications import NotificationCenterView


def _make_manager(tmp_path) -> NotificationManager:
    settings.initialize_app_paths(str(tmp_path), app_id="lgt_app")
    settings.load_settings()
    settings.current_settings["notifications"] = {
        "enabled": True,
        "sound_enabled": False,
    }
    return NotificationManager()


def test_panel_starts_empty(qtbot, tmp_path):
    manager = _make_manager(tmp_path)
    view = NotificationCenterView(manager)
    qtbot.addWidget(view)

    assert view.items_layout.count() == 1  # only the trailing stretch
    assert not view.no_notifications_label.isHidden()
    assert view.scroll_area.isHidden()


def test_panel_lists_and_removes_notifications(qtbot, tmp_path):
    manager = _make_manager(tmp_path)
    view = NotificationCenterView(manager)
    qtbot.addWidget(view)

    notification_id = manager.show_notification(
        type=NotificationType.WARNING, text="Provider is rate limited."
    )

    assert view.items_layout.count() == 2  # row + stretch
    assert view.no_notifications_label.isHidden()
    assert not view.scroll_area.isHidden()
    assert view.scroll_area.height() > 0

    manager.remove_notification(notification_id)

    assert view.items_layout.count() == 1
    assert not view.no_notifications_label.isHidden()


def test_panel_clears_with_history(qtbot, tmp_path):
    manager = _make_manager(tmp_path)
    view = NotificationCenterView(manager)
    qtbot.addWidget(view)

    manager.show_notification(type=NotificationType.INFO, text="One")
    manager.show_notification(type=NotificationType.ERROR, text="Two")
    assert view.items_layout.count() == 3

    manager.clear_history()

    assert view.items_layout.count() == 1
    assert not view.no_notifications_label.isHidden()


def test_bell_opens_a_flyout(qtbot, tmp_path):
    from omni_trans_core.ui.widgets.notifications import NotificationBell

    manager = _make_manager(tmp_path)
    bell = NotificationBell(manager)
    qtbot.addWidget(bell)

    bell._on_bell_clicked()
    qtbot.waitUntil(lambda: bell._flyout is not None and bell._flyout.isVisible())

    assert bell._flyout.isVisible()

    bell._flyout.close()
    qtbot.waitUntil(lambda: bell._flyout is None)
