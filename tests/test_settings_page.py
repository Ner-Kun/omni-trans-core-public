import pytest

from omni_trans_core.ui.pages.settings_page import SettingsPage


@pytest.fixture
def page(qtbot):
    widget = SettingsPage(
        {
            "user_language": "en",
            "log_level": "INFO",
            "log_to_file": False,
            "translation_mode_enabled": False,
        },
        [
            {"name": "English", "code": "en"},
            {"name": "Ukrainian", "code": "uk"},
        ],
        True,
    )
    qtbot.addWidget(widget)
    return widget


def test_language_change_updates_settings_and_emits(page, qtbot):
    with qtbot.waitSignal(page.language_changed, timeout=1000) as blocker:
        page.language_combo.setCurrentIndex(1)

    assert blocker.args == ["uk"]
    assert page.settings_data["user_language"] == "uk"


def test_log_to_file_toggle_emits(page, qtbot):
    with qtbot.waitSignal(page.logging_changed, timeout=1000):
        page.log_to_file_card.setChecked(True)

    assert page.settings_data["log_to_file"] is True


def test_log_level_change_emits(page, qtbot):
    with qtbot.waitSignal(page.logging_changed, timeout=1000):
        page.log_level_combo.setCurrentIndex(0)

    assert page.settings_data["log_level"] == "DEBUG"


def test_provider_buttons_emit(page):
    emitted = []
    page.connections_requested.connect(lambda: emitted.append("connections"))
    page.proxy_requested.connect(lambda: emitted.append("proxy"))

    page.connections_card.clicked.emit()
    page.proxy_card.clicked.emit()

    assert emitted == ["connections", "proxy"]


def test_clear_cache_emits(page):
    emitted = []
    page.cache_clear_requested.connect(lambda: emitted.append("cache"))
    page.clear_cache_card.clicked.emit()

    assert emitted == ["cache"]
