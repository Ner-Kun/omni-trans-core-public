import os
import subprocess
import sys

from PySide6.QtCore import QObject, QThreadPool, QTimer, Slot
from launcher import config
from launcher.models.app_model import AppData
from launcher.models.catalog_model import CatalogModel
from launcher.utils.app_manager import AppManager
from launcher.utils.thread_worker import Worker
from launcher.ui.widgets import SmartButton


class CatalogController(QObject):

    def __init__(self, model: CatalogModel, parent=None):
        super().__init__(parent)
        self.model = model
        self.app_manager = AppManager()
        self.threadpool = QThreadPool()

    @Slot()
    def load_catalog(self):
        self.model.set_status("Loading catalog...", "cyan")

        worker = Worker(self.app_manager.get_catalog)
        worker.signals.result.connect(self._on_catalog_loaded)
        worker.signals.error.connect(self._on_error)
        self.threadpool.start(worker)

    @Slot()
    def force_refresh_catalog(self):
        self.model.set_status("User requested catalog refresh.", "yellow")
        self.load_catalog()

    @Slot(object)
    def _on_catalog_loaded(self, result_tuple):
        apps_data, is_online = result_tuple

        count = len(apps_data)
        offline_tag = " (Offline)" if not is_online else ""
        self.model.set_status(f"Loaded {count} apps.{offline_tag}", "green")

        apps = [AppData.from_dict(data) for data in apps_data]

        for i, app in enumerate(apps):
            if i < len(apps_data):
                app.icon = self.app_manager.get_icon(apps_data[i])

        self.model.set_catalog(apps, is_online)

        core_ver = self.app_manager.get_core_version()
        core_update = self.app_manager.get_core_update_info()
        self.model.set_core_info(core_ver, core_update)

    @Slot(object)
    def select_app(self, app: AppData):
        self.model.select_app(app)

    @Slot()
    def start_installation(self):
        app = self.model.selected_app
        if not app:
            return

        self.model.set_status(f"Initiating install/update for {app.name}", "cyan")

        if app.folder_name == "launcher":
            return

        is_ok, err = self.app_manager.check_dependencies(app.to_dict())
        if not is_ok:
            self.model.set_status(f"Dependency check failed: {err}", "bold red")
            self.model.set_error(f"Update Core first!\n\n{err}")
            return

        self.model.set_status(f"Downloading {app.name}...", "cyan")

        worker = Worker(self.app_manager.install_app, app.to_dict())
        worker.signals.result.connect(self._on_install_finished)
        worker.signals.error.connect(self._on_error)
        self.threadpool.start(worker)

    @Slot()
    def _on_install_finished(self):
        self.model.set_status("Installation done.", "green")
        QTimer.singleShot(100, self.load_catalog)

    @Slot()
    def update_core(self):
        core_data = self.app_manager.get_core_manifest_data()
        if not core_data:
            return

        install_data = core_data.copy()
        install_data["name"] = "Omni Trans Core"
        install_data["folder_name"] = "omni_trans_core"
        install_data["id"] = "core"

        self.model.set_status("Updating Core...", "cyan")

        worker = Worker(self.app_manager.install_app, install_data)
        worker.signals.result.connect(self._on_core_update_finished)
        worker.signals.error.connect(self._on_error)
        self.threadpool.start(worker)

    @Slot()
    def _on_core_update_finished(self):
        self.model.set_status("Core updated.", "green")
        QTimer.singleShot(100, self.load_catalog)

    @Slot(str)
    def start_launch_sequence(self, folder_name: str):
        app = self.model.selected_app
        if not app:
            return

        show, count = self.app_manager.register_launch_and_check_nag(
            folder_name, is_launcher=False
        )

        if show:
            self.model.set_status(f"Nag dialog needed (count: {count})", "cyan")

        is_valid, err = self.app_manager.validate_launch(folder_name)
        if not is_valid:
            self.model.set_status(f"Launch validation failed: {err}", "red")
            self.model.set_error(err)
            return

        self.model.set_status("Checking environment...", "cyan")

        worker = Worker(self.app_manager.run_app_checks, folder_name)
        worker.signals.result.connect(self._execute_app)
        worker.signals.error.connect(self._on_error)
        self.threadpool.start(worker)

    @Slot(str)
    def _execute_app(self, folder_name: str):
        self.model.set_status("Launching...", "green")

        app_path = config.APPS_DIR / folder_name / "runner.py"
        if not app_path.exists():
            self.model.set_status("runner.py not found", "red")
            return

        env = os.environ.copy()
        env["PYTHONPATH"] = str(config.ROOT_DIR) + os.pathsep + env.get("PYTHONPATH", "")
        env["FORCE_COLOR"] = "1"

        try:
            subprocess.Popen(
                [str(config.VENV_PYTHON), str(app_path)],
                env=env,
                cwd=config.ROOT_DIR,
            )
            action_btn = self.parent().action_btn
            action_btn.update_state(SmartButton.STATE_CLOSING, "5")
            for i in range(5, 0, -1):
                QTimer.singleShot((5 - i) * 1000, lambda count=i: action_btn.update_state(SmartButton.STATE_CLOSING, str(count)))
            QTimer.singleShot(5000, lambda: sys.exit(0))
        except Exception as e:
            self._on_error((None, e, None))

    @Slot(tuple)
    def _on_error(self, err_tuple):
        exctype, value, tb_str = err_tuple
        self.model.set_status(f"Error: {value}", "bold red")
        self.model.set_error(str(value))

