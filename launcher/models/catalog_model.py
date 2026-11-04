from typing import Optional
from PySide6.QtCore import QObject, Signal

from launcher.models.app_model import AppData


class CatalogModel(QObject):
    catalog_loaded = Signal(list)
    app_selected = Signal(AppData)
    app_state_changed = Signal(object)
    core_version_updated = Signal(str)
    core_update_available = Signal(object)
    status_changed = Signal(str, str)
    error_occurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._apps: list[AppData] = []
        self._selected_app: Optional[AppData] = None
        self._is_online: bool = False
        self._core_version: str = "Unknown"
        self._core_update_info: object = None

    @property
    def apps(self) -> list[AppData]:
        return self._apps

    @property
    def selected_app(self) -> Optional[AppData]:
        return self._selected_app

    @property
    def is_online(self) -> bool:
        return self._is_online

    @property
    def core_version(self) -> str:
        return self._core_version

    @property
    def core_update_info(self) -> object:
        return self._core_update_info

    def set_catalog(self, apps: list[AppData], is_online: bool):
        self._apps = apps
        self._is_online = is_online
        self.catalog_loaded.emit(apps)

    def select_app(self, app: AppData):
        self._selected_app = app
        self.app_selected.emit(app)

    def set_core_info(self, version: str, update_info: object = None):
        self._core_version = version
        self._core_update_info = update_info
        self.core_version_updated.emit(version)
        if update_info:
            self.core_update_available.emit(update_info)

    def set_status(self, message: str, style: str = "bold blue"):
        self.status_changed.emit(message, style)

    def set_error(self, message: str):
        self.error_occurred.emit(message)