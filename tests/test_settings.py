"""Tests for the split global/app settings storage.

Every test runs against ``tmp_path`` only. The module keeps its paths and
state in module-level globals, so an autouse fixture snapshots and restores
all of them: a failing test must not leak a path into the real ``settings/``
directory or into the next test.
"""
import copy
from pathlib import Path

import pytest

from omni_trans_core import settings


PATH_GLOBALS = (
    "PROJECT_ROOT",
    "SETTINGS_DIR",
    "CONNECTIONS_DIR",
    "OLD_SETTINGS_JSON_FILE",
    "SETTINGS_FILE",
    "LOG_FILE",
    "MODELS_DEV_CACHE_FILE",
    "GLOBAL_SETTINGS_DIR",
    "GLOBAL_SETTINGS_FILE",
    "GLOBAL_CONNECTIONS_DIR",
    "GLOBAL_PROMPTS_DIR",
    "GLOBAL_CRASH_LOGS_DIR",
    "NOTIFICATIONS_HISTORY_FILE",
    "APP_SETTINGS_DIR",
    "APP_SETTINGS_FILE",
    "APP_PROMPTS_DIR",
    "CURRENT_APP_ID",
)

STATE_GLOBALS = ("current_settings", "_global_settings", "_app_settings")

# Defaults are restored too: a source bug that mutates them in place must not
# poison other tests in the same session.
DEFAULT_GLOBALS = ("default_global_settings", "default_app_settings")


@pytest.fixture(autouse=True)
def isolated_settings():
    """Snapshot every mutable settings global, then neutralise it.

    Neutralising first means an accidental call that forgets to initialise
    paths cannot reach the real project: empty strings are falsy and the
    loaders short-circuit on them.
    """
    saved = {
        name: copy.deepcopy(getattr(settings, name))
        for name in PATH_GLOBALS + STATE_GLOBALS + DEFAULT_GLOBALS
    }
    try:
        for name in PATH_GLOBALS:
            setattr(settings, name, "")
        settings.current_settings = {}
        settings._global_settings = {}
        settings._app_settings = {}
        yield
    finally:
        for name, value in saved.items():
            setattr(settings, name, value)


def _init(tmp_path, app_id="lgt_app"):
    settings.initialize_app_paths(str(tmp_path), app_id=app_id)


def _forget_in_memory_state():
    """Drop everything but the on-disk files, so reloads prove persistence."""
    settings._global_settings = {}
    settings._app_settings = {}
    settings.current_settings = {}


def test_initialize_app_paths_builds_app_scoped_paths(tmp_path):
    _init(tmp_path)

    app_dir = tmp_path / "settings" / "lgt_app"
    assert Path(settings.APP_SETTINGS_DIR) == app_dir
    assert Path(settings.APP_SETTINGS_FILE) == app_dir / "app_settings.yaml"
    assert Path(settings.APP_PROMPTS_DIR) == app_dir / "prompts"
    assert settings.CURRENT_APP_ID == "lgt_app"


def test_get_prompts_dir_follows_app_scope(tmp_path):
    _init(tmp_path, app_id="lgt_app")
    assert settings.get_prompts_dir() == settings.APP_PROMPTS_DIR

    # This is the state initialize_app_paths() leaves behind when no app_id
    # is resolved. Set it directly: resolving app_id from the call stack is
    # broken under pytest (see the migration guard test below).
    settings.APP_PROMPTS_DIR = ""
    assert settings.get_prompts_dir() == settings.GLOBAL_PROMPTS_DIR


def test_save_load_roundtrip_splits_global_and_app_keys(tmp_path):
    _init(tmp_path)
    settings.load_settings()

    settings.current_settings["user_language"] = "ru"
    settings.current_settings["recent_files"] = [
        "C:/books/first.lb",
        "C:/books/second.lb",
    ]
    settings.save_settings()

    assert Path(settings.GLOBAL_SETTINGS_FILE).exists()
    assert Path(settings.APP_SETTINGS_FILE).exists()

    _forget_in_memory_state()
    settings.load_settings()

    assert settings.current_settings["user_language"] == "ru"
    assert settings.current_settings["recent_files"] == [
        "C:/books/first.lb",
        "C:/books/second.lb",
    ]


def test_defaults_are_deep_copied(tmp_path):
    _init(tmp_path)
    settings.load_settings()
    assert settings.current_settings["notifications"]["enabled"] is True

    settings.current_settings["notifications"]["enabled"] = False

    assert settings.default_global_settings["notifications"]["enabled"] is True


def test_session_only_keys_are_not_persisted(tmp_path):
    session_only = {
        "translation_mode_enabled": True,
        "ux_t_count": 5,
        "ux_dialog_shown": True,
        "active_connections_list": ["Google Gemini"],
    }

    _init(tmp_path)
    settings.load_settings()
    settings.current_settings.update(session_only)
    settings.save_settings()

    for path in (settings.GLOBAL_SETTINGS_FILE, settings.APP_SETTINGS_FILE):
        persisted = Path(path).read_text(encoding="utf-8")
        for key in session_only:
            assert key not in persisted, f"{key} leaked into {path}"

    _forget_in_memory_state()
    settings.load_settings()

    for key in session_only:
        assert key not in settings.current_settings


def test_atomic_save_leaves_no_tmp_files(tmp_path):
    _init(tmp_path)
    settings.load_settings()
    settings.current_settings["user_language"] = "uk"
    settings.save_settings()

    for directory in (settings.GLOBAL_SETTINGS_DIR, settings.APP_SETTINGS_DIR):
        leftovers = sorted(Path(directory).glob("*.tmp"))
        assert leftovers == [], f"leftover temp files in {directory}"


def test_legacy_migration_aborts_when_app_id_is_unknown(tmp_path):
    """A runner.py outside PROJECT_ROOT must not be treated as the app runner.

    Pytest ships ``_pytest/runner.py``; the resolver only accepts a runner
    that lives directly under PROJECT_ROOT, so this call resolves app_id=''
    and the migration guard fires.
    """
    legacy_file = tmp_path / "settings" / "app_settings.yaml"
    legacy_file.parent.mkdir(parents=True)
    legacy_file.write_text(
        "\n".join(
            [
                "user_language: ru",
                "theme_name: dark",
                'CORE_VERSION: "1.0.0"',
                "recent_files:",
                "  - C:/books/a.lb",
                "target_languages:",
                "  - Ukrainian",
                "",
            ]
        ),
        encoding="utf-8",
    )

    settings.initialize_app_paths(str(tmp_path))
    settings.load_settings()

    assert legacy_file.exists(), "old file must survive an aborted migration"
    assert not Path(settings.GLOBAL_SETTINGS_FILE).exists(), (
        "migration must not write globals when app keys would be lost"
    )


def test_legacy_migration_aborts_when_app_id_cannot_be_resolved(tmp_path, monkeypatch):
    """Same guard, with the fragile stack heuristic neutralised.

    This isolates the migration logic itself from the app_id resolution bug
    covered by the test above.
    """

    class _NoStack:
        @staticmethod
        def stack():
            return []

    monkeypatch.setattr(settings, "inspect", _NoStack)

    legacy_file = tmp_path / "settings" / "app_settings.yaml"
    legacy_file.parent.mkdir(parents=True)
    legacy_file.write_text(
        "\n".join(
            [
                "user_language: ru",
                "theme_name: dark",
                "recent_files:",
                "  - C:/books/a.lb",
                "",
            ]
        ),
        encoding="utf-8",
    )

    settings.initialize_app_paths(str(tmp_path))
    assert settings.CURRENT_APP_ID == ""
    settings.load_settings()

    assert legacy_file.exists()
    assert not Path(settings.GLOBAL_SETTINGS_FILE).exists()


def test_active_prompt_profile_persists_as_global_key(tmp_path):
    _init(tmp_path)
    settings.load_settings()

    settings.current_settings["active_prompt_profile"] = "My Custom Profile"
    settings.save_settings()

    _forget_in_memory_state()
    settings.load_settings()

    assert settings.current_settings["active_prompt_profile"] == "My Custom Profile"
