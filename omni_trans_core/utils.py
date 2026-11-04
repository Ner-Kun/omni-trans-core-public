import logging
from typing import Any, Callable
from . import settings
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import QObject
from functools import wraps
from .localization_manager import translate

logger = logging.getLogger('CORE.utils')


def wip_notification(
    message_key: str, mode: str = "info", settings_key: str | None = None
):
    def decorator(func: Callable[..., Any]):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if settings_key is not None and settings.current_settings.get(
                settings_key, False
            ):
                return func(*args, **kwargs)
            title = translate("dialog.wip.title")
            message = translate(message_key)
            if mode == "info":
                QtWidgets.QMessageBox.information(None, title, message)
                return func(*args, **kwargs)
            elif mode == "confirm":
                msg_box = QtWidgets.QMessageBox()
                msg_box.setWindowTitle(title)
                msg_box.setText(message)
                msg_box.setStandardButtons(
                    QtWidgets.QMessageBox.StandardButton.Yes
                    | QtWidgets.QMessageBox.StandardButton.Cancel
                )
                msg_box.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Yes)
                msg_box.button(QtWidgets.QMessageBox.StandardButton.Yes).setText(
                    "Continue"
                )
                dont_show_again_checkbox = None
                if settings_key:
                    dont_show_again_checkbox = QtWidgets.QCheckBox(
                        translate("dialog.wip.checkbox_dont_show_again")
                    )
                    msg_box.setCheckBox(dont_show_again_checkbox)
                reply = msg_box.exec()
                if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                    if (
                        dont_show_again_checkbox
                        and dont_show_again_checkbox.isChecked()
                        and settings_key is not None
                    ):
                        settings.current_settings[settings_key] = True
                        settings.save_settings()
                    return func(*args, **kwargs)
                else:
                    return None
            return func(*args, **kwargs)

        return wrapper

    return decorator


def mask_api_key(api_key_string: str) -> str:
    if not api_key_string:
        return "N/A_KEY"
    if len(api_key_string) > 7:
        return f"{api_key_string[:3]}...{api_key_string[-4:]}"
    elif len(api_key_string) > 0:
        return "****"
    return "EMPTY_KEY"


def get_model_clean_name(full_model_id: str) -> str:
    return full_model_id.split('/')[-1] if '/' in full_model_id else full_model_id


class DebounceTimer(QtCore.QObject):
    _slot: Callable[[], None]
    _timer: QtCore.QTimer

    def __init__(
        self, slot: Callable[[], None], interval_ms: int, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._slot = slot
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(interval_ms)
        _ = self._timer.timeout.connect(self._slot)

    def trigger(self) -> None:
        self._timer.start()

    def force_run(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self._slot()

    def cancel(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
