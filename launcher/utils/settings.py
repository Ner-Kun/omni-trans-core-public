import json
from pathlib import Path

from launcher import config

DEFAULT_SETTINGS = {
    "close_after_launch": True,
    "minimize_to_tray": False,
    "check_updates_on_startup": True,
    "remember_last_app": True,
    "last_selected_app": "",
}


class LauncherSettings:
    """Small persistent settings store for the launcher itself."""

    def __init__(self, path: Path | None = None):
        self.path = path or config.LAUNCHER_SETTINGS_JSON
        self._data = DEFAULT_SETTINGS.copy()
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        if not isinstance(data, dict):
            return

        for key in DEFAULT_SETTINGS:
            if key in data:
                self._data[key] = data[key]

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_suffix(".tmp")
            temp_path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            temp_path.replace(self.path)
        except OSError:
            pass

    @property
    def close_after_launch(self) -> bool:
        return bool(self._data.get("close_after_launch", True))

    @close_after_launch.setter
    def close_after_launch(self, value: bool) -> None:
        self._data["close_after_launch"] = bool(value)

    @property
    def minimize_to_tray(self) -> bool:
        return bool(self._data.get("minimize_to_tray", False))

    @minimize_to_tray.setter
    def minimize_to_tray(self, value: bool) -> None:
        self._data["minimize_to_tray"] = bool(value)

    @property
    def check_updates_on_startup(self) -> bool:
        return bool(self._data.get("check_updates_on_startup", True))

    @check_updates_on_startup.setter
    def check_updates_on_startup(self, value: bool) -> None:
        self._data["check_updates_on_startup"] = bool(value)

    @property
    def remember_last_app(self) -> bool:
        return bool(self._data.get("remember_last_app", True))

    @remember_last_app.setter
    def remember_last_app(self, value: bool) -> None:
        self._data["remember_last_app"] = bool(value)

    @property
    def last_selected_app(self) -> str:
        return str(self._data.get("last_selected_app", "") or "")

    @last_selected_app.setter
    def last_selected_app(self, value: str) -> None:
        self._data["last_selected_app"] = str(value or "")
