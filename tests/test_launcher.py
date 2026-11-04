import json
import shutil
import zipfile
from pathlib import Path

import pytest

from launcher.models.app_model import AppData
from launcher.utils import app_manager as app_manager_module


def _make_app_archive(path: Path, version: str = "1.0.0") -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "test_app/constants.py",
            f'APP_NAME = "Test App"\nAPP_VERSION = "{version}"\n',
        )
        zf.writestr("test_app/runner.py", "print('hello')\n")


@pytest.fixture
def launcher_config(tmp_path, monkeypatch):
    from launcher import config

    apps_dir = tmp_path / "apps"
    temp_dir = tmp_path / "temp"
    data_dir = tmp_path / "data"
    apps_dir.mkdir()
    temp_dir.mkdir()
    data_dir.mkdir()

    monkeypatch.setattr(config, "APPS_DIR", apps_dir)
    monkeypatch.setattr(config, "TEMP_DIR", temp_dir)
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "INSTALLED_APPS_JSON", data_dir / "installed_apps.json")
    monkeypatch.setattr(config, "LAUNCHER_SETTINGS_JSON", data_dir / "settings.json")
    monkeypatch.setattr(config, "MANIFEST_URL", str(tmp_path / "manifest.json"))
    return config


def test_appdata_from_dict_keeps_local_update_state():
    data = {
        "folder_name": "lgt_app",
        "name": "Lorebook Gemini Translator",
        "version": "0.3.0",
        "update_available": True,
        "critical": True,
        "changelog": "new",
        "exe_path": "runner.py",
        "archive_name": "lgt_app.zip",
    }
    local = {
        "version": "0.2.0",
        "pending_update_version": "0.3.0",
        "pending_changelog": "new",
        "is_critical": True,
        "exe_path": "app.py",
    }

    app = AppData.from_dict(data, local)

    assert app.is_local is True
    assert app.local_version == "0.2.0"
    assert app.latest_version == "0.3.0"
    assert app.update_available is True
    assert app.is_critical is True
    assert app.exe_path == "app.py"
    assert app.to_dict()["archive_name"] == "lgt_app.zip"


def test_install_app_replaces_target_and_preserves_launch_count(
    launcher_config, tmp_path, monkeypatch
):
    archive = tmp_path / "test_app.zip"
    _make_app_archive(archive)

    target = launcher_config.APPS_DIR / "test_app"
    target.mkdir()
    (target / "old.txt").write_text("old", encoding="utf-8")
    launcher_config.INSTALLED_APPS_JSON.write_text(
        json.dumps({"test_app": {"launch_count": 7, "install_date": "2026-01-01"}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        app_manager_module,
        "_download_archive",
        lambda _url, destination: shutil.copyfile(archive, destination),
    )

    manager = app_manager_module.AppManager()
    result = manager.install_app(
        {
            "folder_name": "test_app",
            "name": "Test App",
            "repo_url": "https://example.com/test_app",
            "latest_version": "1.0.0",
        }
    )

    assert result["version"] == "1.0.0"
    assert (target / "runner.py").exists()
    assert not (target / "old.txt").exists()

    registry = json.loads(
        launcher_config.INSTALLED_APPS_JSON.read_text(encoding="utf-8")
    )
    assert registry["test_app"]["version"] == "1.0.0"
    assert registry["test_app"]["launch_count"] == 7
    assert registry["test_app"]["install_date"] == "2026-01-01"


def test_clean_changelog_strips_generic_heading_and_note():
    from launcher.utils.changelog import clean_changelog

    body, note = clean_changelog(
        "**Note:** Showing notes for latest release (v0.2.1-alpha).\n\n"
        "# Changelog\n\n"
        "## v0.2.1-alpha\n\n"
        "- Fix Gemini 3\n"
    )

    assert note == "Showing notes for latest release (v0.2.1-alpha)."
    assert body.startswith("## v0.2.1-alpha")
    assert "# Changelog" not in body


def test_launcher_settings_roundtrip(tmp_path):
    from launcher.utils.settings import LauncherSettings

    path = tmp_path / "settings.json"
    settings = LauncherSettings(path)
    assert settings.close_after_launch is True
    assert settings.minimize_to_tray is False
    assert settings.check_updates_on_startup is True
    assert settings.remember_last_app is True

    settings.close_after_launch = False
    settings.minimize_to_tray = True
    settings.check_updates_on_startup = False
    settings.remember_last_app = False
    settings.last_selected_app = "lgt_app"
    settings.save()

    loaded = LauncherSettings(path)
    assert loaded.close_after_launch is False
    assert loaded.minimize_to_tray is True
    assert loaded.check_updates_on_startup is False
    assert loaded.remember_last_app is False
    assert loaded.last_selected_app == "lgt_app"


def test_is_app_running_matches_process_command(launcher_config, monkeypatch):
    from types import SimpleNamespace

    from launcher.utils import app_manager as module

    launcher_config.INSTALLED_APPS_JSON.write_text(
        json.dumps({"test_app": {"exe_path": "runner.py"}}),
        encoding="utf-8",
    )
    manager = module.AppManager()
    app_path = launcher_config.APPS_DIR / "test_app" / "runner.py"

    fake_process = SimpleNamespace(
        pid=123,
        info={"cmdline": [str(launcher_config.VENV_PYTHON), str(app_path)]},
    )
    monkeypatch.setattr(
        module.psutil, "process_iter", lambda *_args: [fake_process]
    )
    assert manager.is_app_running("test_app") is True

    fake_process.info["cmdline"] = ["python", "-c", "print('unrelated')"]
    assert manager.is_app_running("test_app") is False


def test_app_detail_running_state(qapp):
    from launcher.models.app_model import AppData
    from launcher.ui.pages.apps_page import AppDetailWidget

    detail = AppDetailWidget()
    app = AppData(
        folder_name="test_app",
        name="Test App",
        is_local=True,
        is_running=True,
    )

    detail.set_app(app)

    assert detail.action_btn.text() == "Running"
    assert not detail.action_btn.isEnabled()
    assert detail.state_badge.text() == "Running"


def test_app_detail_launching_state(qapp):
    from launcher.models.app_model import AppData
    from launcher.ui.pages.apps_page import AppDetailWidget

    detail = AppDetailWidget()
    app = AppData(
        folder_name="test_app",
        name="Test App",
        is_local=True,
        is_launching=True,
    )

    detail.set_app(app)

    assert detail.action_btn.text() == "Launching..."
    assert not detail.action_btn.isEnabled()
    assert detail.state_badge.text() == "Launching"


def test_launcher_update_info_uses_pending_version(launcher_config):
    launcher_config.INSTALLED_APPS_JSON.write_text(
        json.dumps(
            {
                "launcher": {
                    "version": "1.0.0",
                    "pending_update_version": "1.1.0",
                    "pending_changelog": "notes",
                    "archive_name": "launcher.zip",
                    "repo_url": "https://example.com/launcher",
                }
            }
        ),
        encoding="utf-8",
    )

    manager = app_manager_module.AppManager()
    info = manager.get_launcher_update_info()

    assert info is not None
    assert info["latest_version"] == "1.1.0"
    assert info["changelog"] == "notes"
    assert info["archive_name"] == "launcher.zip"


def test_swap_folder_rolls_back_when_move_fails(tmp_path, monkeypatch):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "new.txt").write_text("new", encoding="utf-8")
    (target / "old.txt").write_text("old", encoding="utf-8")

    def fail_move(_source, _target):
        raise OSError("disk is full")

    monkeypatch.setattr(app_manager_module.shutil, "move", fail_move)

    with pytest.raises(OSError):
        app_manager_module._swap_folder(source, target)

    assert (target / "old.txt").read_text(encoding="utf-8") == "old"
    assert not (target.with_name("target.backup")).exists()


def test_safe_extract_rejects_path_traversal(tmp_path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../evil.txt", "evil")

    with pytest.raises(ValueError, match="Unsafe archive member"):
        app_manager_module._safe_extract(archive, tmp_path / "extract")

    assert not (tmp_path / "evil.txt").exists()


def test_execute_app_uses_registry_exe_path(
    qapp, launcher_config, tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from launcher.controllers.catalog_controller import CatalogController
    from launcher.models.catalog_model import CatalogModel

    app_dir = launcher_config.APPS_DIR / "test_app"
    app_dir.mkdir()
    (app_dir / "custom.py").write_text("print('ok')\n", encoding="utf-8")
    launcher_config.INSTALLED_APPS_JSON.write_text(
        json.dumps({"test_app": {"exe_path": "custom.py"}}),
        encoding="utf-8",
    )

    calls = []
    monkeypatch.setattr(
        "launcher.controllers.catalog_controller.subprocess.Popen",
        lambda cmd, **_kwargs: (
            calls.append(cmd)
            or SimpleNamespace(pid=999999, poll=lambda: None)
        ),
    )

    model = CatalogModel()
    controller = CatalogController(model)
    launched = []
    controller.launch_started.connect(launched.append)

    controller._execute_app("test_app")

    assert calls
    assert Path(calls[0][1]).name == "custom.py"
    assert launched == ["test_app"]


def test_launcher_window_constructs(
    qtbot, qapp, launcher_config, tmp_path, monkeypatch
):
    (tmp_path / "manifest.json").write_text(
        json.dumps({"apps": []}),
        encoding="utf-8",
    )

    from launcher.controllers.catalog_controller import CatalogController
    from launcher.ui.main_window import LauncherWindow
    from launcher.ui.styles import setup_theme

    monkeypatch.setattr(CatalogController, "load_catalog", lambda self: None)
    monkeypatch.setattr(LauncherWindow, "_check_launcher_nag", lambda self: None)

    setup_theme(qapp)
    window = LauncherWindow()
    qtbot.addWidget(window)

    assert window.apps_page.objectName() == "appsPage"
    assert window.about_page.objectName() == "aboutPage"
    assert window.apps_page.app_list.count() == 0

    window.close()
    window.deleteLater()
    qapp.processEvents()
