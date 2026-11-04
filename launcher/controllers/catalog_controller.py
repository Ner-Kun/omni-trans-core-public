import os
import subprocess

from PySide6.QtCore import QObject, QThreadPool, QTimer, Signal, Slot

from launcher import config
from launcher.models.app_model import AppData
from launcher.models.catalog_model import CatalogModel
from launcher.utils.app_manager import AppManager
from launcher.utils.thread_worker import Worker
from launcher.utils.window_watcher import AppWindowWatcher


class CatalogController(QObject):
    busy_changed = Signal(bool, str)
    install_finished = Signal(str)
    core_update_finished = Signal()
    launcher_update_started = Signal()
    launch_started = Signal(str)
    app_window_ready = Signal(str)
    app_window_timeout = Signal(str)
    app_launch_failed = Signal(str, str)
    nag_required = Signal(str, int)

    def __init__(self, model: CatalogModel, parent=None):
        super().__init__(parent)
        self.model = model
        self.app_manager = AppManager()
        self.threadpool = QThreadPool()
        self._catalog_loading = False
        self._operation_running = False
        self._busy_message = ""
        self._watchers: dict[str, AppWindowWatcher] = {}
        self._launching_folders: set[str] = set()
        self.last_updates_checked = True

    def is_busy(self) -> bool:
        return self._operation_running

    def _emit_busy(self, message: str = "") -> None:
        if message:
            self._busy_message = message

        busy = self._operation_running or self._catalog_loading
        if not busy:
            self._busy_message = ""

        self.busy_changed.emit(busy, self._busy_message if busy else "")

    def load_catalog(self, check_updates: bool = True):
        if self._catalog_loading:
            return

        self.last_updates_checked = check_updates
        self._catalog_loading = True
        self.model.set_status("Loading catalog...", "cyan")
        self._emit_busy("Loading catalog...")

        worker = Worker(self.app_manager.get_catalog, check_updates)
        worker.signals.result.connect(self._on_catalog_loaded)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_catalog_finished)
        self.threadpool.start(worker)

    @Slot()
    def _on_catalog_finished(self):
        self._catalog_loading = False
        self._emit_busy()

    @Slot()
    def force_refresh_catalog(self):
        self.model.set_status("Refreshing catalog...", "yellow")
        self.load_catalog(check_updates=True)

    @Slot(object)
    def _on_catalog_loaded(self, result_tuple):
        apps_data, is_online = result_tuple

        count = len(apps_data)
        offline_tag = " (offline)" if not is_online else ""
        self.model.set_status(f"Loaded {count} apps{offline_tag}.", "green")

        apps = [AppData.from_dict(data) for data in apps_data]
        for app, raw_data in zip(apps, apps_data):
            app.icon = self.app_manager.get_icon(raw_data)
            app.is_launching = app.folder_name in self._launching_folders

        self.model.set_catalog(apps, is_online)

        core_ver = self.app_manager.get_core_version()
        core_update = self.app_manager.get_core_update_info()
        self.model.set_core_info(core_ver, core_update)

    @Slot(object)
    def select_app(self, app: AppData):
        self.model.select_app(app)

    def refresh_running_states(self) -> None:
        for app in self.model.apps:
            running = self.app_manager.is_app_running(app.folder_name)
            if app.is_running != running:
                app.is_running = running
                self.model.app_state_changed.emit(app)

    @Slot()
    def start_installation(self):
        app = self.model.selected_app
        if not app or self._operation_running:
            return

        if app.folder_name == "launcher":
            return

        if app.is_running or app.is_launching:
            self.model.set_error(
                f"Close {app.name} before updating."
            )
            return

        is_ok, err = self.app_manager.check_dependencies(app.to_dict())
        if not is_ok:
            self.model.set_status(f"Dependency check failed: {err}", "bold red")
            self.model.set_error(f"Update Core first!\n\n{err}")
            return

        self._operation_running = True
        self._emit_busy(f"Installing {app.name}...")

        worker = Worker(self.app_manager.install_app, app.to_dict())
        worker.signals.result.connect(self._on_install_finished)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_operation_finished)
        self.threadpool.start(worker)

    @Slot(object)
    def _on_install_finished(self, result: dict):
        name = result.get("name", result.get("folder_name", "Application"))
        self.model.set_status(f"{name} is installed.", "green")
        self.install_finished.emit(result.get("folder_name", ""))
        QTimer.singleShot(100, self.load_catalog)

    @Slot()
    def update_core(self):
        core_data = self.app_manager.get_core_manifest_data()
        if not core_data or self._operation_running:
            return

        if any(app.is_running or app.is_launching for app in self.model.apps):
            self.model.set_error(
                "Close running applications before updating the core."
            )
            return

        install_data = core_data.copy()
        install_data["name"] = "Omni Trans Core"
        install_data["folder_name"] = "omni_trans_core"
        install_data["id"] = "core"

        self._operation_running = True
        self._emit_busy("Updating core...")

        worker = Worker(self.app_manager.install_app, install_data)
        worker.signals.result.connect(self._on_core_update_finished)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_operation_finished)
        self.threadpool.start(worker)

    @Slot(object)
    def _on_core_update_finished(self, result: dict):
        self.model.set_status("Core updated.", "green")
        self.core_update_finished.emit()
        QTimer.singleShot(100, self.load_catalog)

    @Slot(object)
    def update_launcher(self, info: dict):
        if self._operation_running:
            return

        if any(app.is_running or app.is_launching for app in self.model.apps):
            self.model.set_error(
                "Close running applications before updating the launcher."
            )
            return

        self._operation_running = True
        self._emit_busy("Updating launcher...")

        worker = Worker(self.app_manager.update_launcher, info)
        worker.signals.result.connect(self._on_launcher_update_finished)
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(self._on_operation_finished)
        self.threadpool.start(worker)

    @Slot(object)
    def _on_launcher_update_finished(self, _result):
        self.launcher_update_started.emit()

    @Slot()
    def _on_operation_finished(self):
        self._operation_running = False
        self._emit_busy()

    @Slot(str)
    def start_launch_sequence(self, folder_name: str):
        app = self.model.selected_app
        if not app or app.is_running or app.is_launching:
            return

        self._set_launching(folder_name, True)

        show, count = self.app_manager.register_launch_and_check_nag(
            folder_name, is_launcher=False
        )
        if show:
            self.nag_required.emit(app.name, count)

        is_valid, err = self.app_manager.validate_launch(folder_name)
        if not is_valid:
            self._set_launching(folder_name, False)
            self.model.set_status(f"Launch validation failed: {err}", "red")
            self.model.set_error(err)
            return

        worker = Worker(self.app_manager.run_app_checks, folder_name)
        worker.signals.result.connect(self._execute_app)
        worker.signals.error.connect(
            lambda err: self._on_launch_error(folder_name, err)
        )
        self.threadpool.start(worker)

    @Slot(str)
    def _execute_app(self, folder_name: str):
        if self.app_manager.is_app_running(folder_name):
            self._set_launching(folder_name, False)
            self.model.set_error(
                "The application is already running."
            )
            return

        exe_path = self.app_manager.get_exe_path(folder_name)
        app_path = config.APPS_DIR / folder_name / exe_path
        if not app_path.exists():
            self._set_launching(folder_name, False)
            self.model.set_status(f"{exe_path} not found", "red")
            self.model.set_error(
                f"Cannot launch {folder_name}: {exe_path} is missing."
            )
            return

        env = os.environ.copy()
        env["PYTHONPATH"] = str(config.ROOT_DIR) + os.pathsep + env.get(
            "PYTHONPATH", ""
        )
        env["FORCE_COLOR"] = "1"

        try:
            process = subprocess.Popen(
                [str(config.VENV_PYTHON), str(app_path)],
                env=env,
                cwd=config.ROOT_DIR,
            )
        except OSError as error:
            self._set_launching(folder_name, False)
            self._on_error((type(error), error, None))
            return

        app_name = self.app_manager.get_app_entry(folder_name).get(
            "name", folder_name
        )
        watcher = AppWindowWatcher(process, parent=self)
        self._watchers[folder_name] = watcher
        watcher.window_ready.connect(
            lambda: self._on_app_window_ready(folder_name)
        )
        watcher.timed_out.connect(
            lambda: self._on_app_window_timeout(folder_name)
        )
        watcher.process_exited.connect(
            lambda: self._on_app_process_exited(folder_name)
        )
        watcher.start()

        self.launch_started.emit(app_name)

    def _on_app_window_ready(self, folder_name: str) -> None:
        self._watchers.pop(folder_name, None)
        self._set_launching(folder_name, False)
        self.app_window_ready.emit(folder_name)
        self.refresh_running_states()

    def _on_app_window_timeout(self, folder_name: str) -> None:
        self._watchers.pop(folder_name, None)
        self._set_launching(folder_name, False)
        self.app_window_timeout.emit(folder_name)

    def _on_app_process_exited(self, folder_name: str) -> None:
        self._watchers.pop(folder_name, None)
        self._set_launching(folder_name, False)
        app_name = self.app_manager.get_app_entry(folder_name).get(
            "name", folder_name
        )
        self.app_launch_failed.emit(
            folder_name,
            f"{app_name} exited before opening its window.",
        )

    def _set_launching(self, folder_name: str, value: bool) -> None:
        if value:
            self._launching_folders.add(folder_name)
        else:
            self._launching_folders.discard(folder_name)

        for app in self.model.apps:
            if app.folder_name != folder_name:
                continue
            if app.is_launching != value:
                app.is_launching = value
                self.model.app_state_changed.emit(app)
            return

    def _on_launch_error(self, folder_name: str, err_tuple) -> None:
        self._set_launching(folder_name, False)
        self._on_error(err_tuple)

    @Slot(tuple)
    def _on_error(self, err_tuple):
        _exctype, value, _tb_str = err_tuple
        self.model.set_status(f"Error: {value}", "bold red")
        self.model.set_error(str(value))
