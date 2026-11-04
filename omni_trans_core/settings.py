import os
import json
import logging
import shutil
import copy
import inspect
from typing import Any
from ruamel.yaml import YAML
from .constants import CORE_VERSION, MAX_RECENT_FILES
from .proxy_manager import proxy_manager

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# === Глобальные пути (проект) ===
PROJECT_ROOT = ""

# === Старые пути (для обратной совместимости) ===
SETTINGS_DIR = ""
CONNECTIONS_DIR = ""
OLD_SETTINGS_JSON_FILE = ""
SETTINGS_FILE = ""
LOG_FILE = ""
MODELS_DEV_CACHE_FILE = ""

# === Новые пути (разделение по приложениям) ===
GLOBAL_SETTINGS_DIR = ""  # settings/global/
GLOBAL_SETTINGS_FILE = ""  # settings/global/app_settings.yaml
GLOBAL_CONNECTIONS_DIR = ""  # settings/global/connections/
GLOBAL_PROMPTS_DIR = ""  # settings/global/prompts/
GLOBAL_CRASH_LOGS_DIR = ""  # settings/global/crash_logs/
NOTIFICATIONS_HISTORY_FILE = ""  # settings/global/notifications_history.json
APP_SETTINGS_DIR = "" # settings/{app_id}/
APP_SETTINGS_FILE = "" # settings/{app_id}/app_settings.yaml
APP_PROMPTS_DIR = ""  # settings/{app_id}/prompts/

# === Текущий app_id ===
CURRENT_APP_ID = ""

PROVIDER_CUSTOM_HEADERS: dict[str, dict[str, str]] = {}

_DEV_TOOLS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "developer_tools.py")
DEV_MODE_ENABLED: bool = os.path.exists(_DEV_TOOLS_PATH)

LITELLM_LOGGING_DISABLED: bool = True

logger = logging.getLogger('CORE.settings')


def get_default_generation_params():
    return {
        "enable_model_thinking": True,
        "thinking_budget_value": -1,
        "thinking_level": "high",
        "use_content_as_context": True,
        "temperature": 1.0,
        "top_p": 1.0,
        "max_output_tokens": 32000,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
    }


# === ОБЩИЕ настройки (global/) ===
default_global_settings: dict[str, Any] = {
    # Legacy Gemini settings: read once by gemini_migration, then unused.
    # Remove together with the legacy UI after one release.
    "api_keys": [],
    "current_api_key_index": 0,
    "active_connection_name": "",
    "active_model_for_connection": {},
    "gemini_generation_params": get_default_generation_params(),
    "gemini_model": "gemini-2.5-flash-lite-preview-06-17",
    "available_gemini_models": [],
    "manual_rpm_control": False,
    "api_request_delay": 6.0,
    "rpm_limit": 15,
    "rpm_warning_threshold_percent": 60,
    "rpm_monitor_update_interval_ms": 1000,
    "api_thread_pool_ratio": 0.75,
    "proxy_enabled": False,
    "proxy_custom_list": [],
    "user_language": "en",
    "log_to_file": False,
    "log_level": "INFO",
    "notifications": {
        "enabled": True,
        "sound_enabled": True,
        "sound_volume": 0.5,
        "max_visible_toasts": 5,
        "toast_auto_hide_ms": 5000,
        "history_max_items": 100,
        "history_save_days": 30,
    },
    "thinking_failure_threshold": 3,
    "CORE_VERSION": CORE_VERSION,
}

# === ИНДИВИДУАЛЬНЫЕ настройки приложения ===
default_app_settings: dict[str, Any] = {
    "recent_files": [],
    "target_languages": [],
    "selected_target_language": "",
    "available_source_languages": ["English"],
    "selected_source_language": "English",
    "auto_save_interval_ms": 5000,
    "active_prompt_profile": "",
    "ux_show_wip_on_startup": True,
}

# === Текущие настройки (объединённые) ===
current_settings: dict[str, Any] = {}

# === Отдельные хранилища для глобальных и app настроек ===
_global_settings: dict[str, Any] = {}
_app_settings: dict[str, Any] = {}


def initialize_app_paths(project_root_path: str, app_id: str | None = None):
    global \
        PROJECT_ROOT, \
        SETTINGS_DIR, CONNECTIONS_DIR, OLD_SETTINGS_JSON_FILE, SETTINGS_FILE, LOG_FILE, MODELS_DEV_CACHE_FILE, \
        GLOBAL_SETTINGS_DIR, GLOBAL_SETTINGS_FILE, GLOBAL_CONNECTIONS_DIR, GLOBAL_PROMPTS_DIR, GLOBAL_CRASH_LOGS_DIR, NOTIFICATIONS_HISTORY_FILE, \
        APP_SETTINGS_DIR, APP_SETTINGS_FILE, APP_PROMPTS_DIR, \
        CURRENT_APP_ID

    PROJECT_ROOT = project_root_path

    # Определяем app_id
    if app_id is None:
        # Fallback: accept only a runner.py that lives directly under PROJECT_ROOT.
        # This skips pytest's _pytest/runner.py and any package-installed runner.
        root = os.path.abspath(PROJECT_ROOT)
        for frame in inspect.stack():
            frame_path = os.path.abspath(frame.filename)
            if os.path.basename(frame_path) != "runner.py":
                continue
            candidate_dir = os.path.dirname(frame_path)
            if os.path.dirname(candidate_dir) != root:
                continue
            app_id = os.path.basename(candidate_dir)
            logger.warning(
                "app_id was not passed explicitly; resolved '%s' from the call stack. "
                "Pass app_id to initialize_app_paths().",
                app_id,
            )
            break

    CURRENT_APP_ID = app_id if app_id else ""
    if not CURRENT_APP_ID:
        logger.error(
            "app_id is not set: app settings will not be persisted and migrations "
            "that need the app scope will be skipped."
        )

    # Старые пути (для обратной совместимости и миграции)
    SETTINGS_DIR = os.path.join(PROJECT_ROOT, "settings")
    CONNECTIONS_DIR = os.path.join(SETTINGS_DIR, "connections")
    OLD_SETTINGS_JSON_FILE = os.path.join(PROJECT_ROOT, "translator_settings.json")
    SETTINGS_FILE = os.path.join(SETTINGS_DIR, "app_settings.yaml")
    LOG_FILE = os.path.join(PROJECT_ROOT, "translator.log")
    MODELS_DEV_CACHE_FILE = os.path.join(SETTINGS_DIR, "models_dev_cache.json")

    # Новые пути (глобальные)
    GLOBAL_SETTINGS_DIR = os.path.join(PROJECT_ROOT, "settings", "global")
    GLOBAL_SETTINGS_FILE = os.path.join(GLOBAL_SETTINGS_DIR, "app_settings.yaml")
    GLOBAL_CONNECTIONS_DIR = os.path.join(GLOBAL_SETTINGS_DIR, "connections")
    GLOBAL_PROMPTS_DIR = os.path.join(GLOBAL_SETTINGS_DIR, "prompts")
    GLOBAL_CRASH_LOGS_DIR = os.path.join(GLOBAL_SETTINGS_DIR, "crash_logs")
    NOTIFICATIONS_HISTORY_FILE = os.path.join(GLOBAL_SETTINGS_DIR, "notifications_history.json")

    # Новые пути (приложения)
    if CURRENT_APP_ID:
        APP_SETTINGS_DIR = os.path.join(PROJECT_ROOT, "settings", CURRENT_APP_ID)
        APP_SETTINGS_FILE = os.path.join(APP_SETTINGS_DIR, "app_settings.yaml")
        APP_PROMPTS_DIR = os.path.join(APP_SETTINGS_DIR, "prompts")
    else:
        APP_SETTINGS_DIR = ""
        APP_SETTINGS_FILE = ""
        APP_PROMPTS_DIR = ""

    logger.debug(f"Initialized paths for app_id='{CURRENT_APP_ID}'")
    logger.debug(f"GLOBAL_SETTINGS_FILE: {GLOBAL_SETTINGS_FILE}")
    logger.debug(f"APP_SETTINGS_FILE: {APP_SETTINGS_FILE}")
    logger.debug(f"APP_PROMPTS_DIR: {APP_PROMPTS_DIR}")


def get_prompts_dir() -> str:
    """Return the prompt profile directory for the current app."""
    return APP_PROMPTS_DIR or GLOBAL_PROMPTS_DIR


def _migrate_settings(loaded_data: dict[str, Any]) -> dict[str, Any]:
    """Миграция старого формата настроек."""
    default_gen_params_keys = get_default_generation_params().keys()
    if any(key in loaded_data for key in default_gen_params_keys):
        logger.info("Old settings format detected. Migrating generation parameters...")
        migrated_gemini_params = get_default_generation_params()
        for key in default_gen_params_keys:
            if key in loaded_data:
                migrated_gemini_params[key] = loaded_data[key]
                del loaded_data[key]
        loaded_data["gemini_generation_params"] = migrated_gemini_params
    if "custom_connections" in loaded_data and isinstance(
        loaded_data["custom_connections"], list
    ):
        for conn in loaded_data["custom_connections"]:
            if isinstance(conn, dict) and "generation_params" not in conn:
                conn["generation_params"] = get_default_generation_params()
            if "custom_enable_thinking" in loaded_data:
                conn["generation_params"]["enable_model_thinking"] = (
                    loaded_data["custom_enable_thinking"]
                )
        for old_key in ["custom_enable_thinking", "custom_reasoning_effort"]:
            if old_key in loaded_data:
                del loaded_data[old_key]
        logger.info("Migration complete.")
    if "api_key" in loaded_data and isinstance(loaded_data["api_key"], str):
        if "api_keys" not in loaded_data:
            loaded_data["api_keys"] = (
                [loaded_data["api_key"]] if loaded_data["api_key"].strip() else []
            )
        logger.info("Migrated old 'api_key' to 'api_keys' list.")
        del loaded_data["api_key"]
    return loaded_data


def _validate_and_clean_settings(settings_data: dict[str, Any]) -> None:
    """Валидация и очистка настроек."""
    if not isinstance(settings_data.get("api_keys"), list):
        settings_data["api_keys"] = []
    num_keys = len(settings_data["api_keys"])
    loaded_idx = settings_data.get("current_api_key_index", 0)
    if not (0 <= loaded_idx < num_keys):
        if num_keys > 0:
            logger.warning(
                f"Loaded current_api_key_index {loaded_idx} out of bounds ({num_keys} keys). Resetting to 0."
            )
        settings_data["current_api_key_index"] = 0
    conns = settings_data.get("custom_connections", [])
    if isinstance(conns, list):
        for conn in conns:
            if isinstance(conn, dict) and "generation_params" not in conn:
                conn["generation_params"] = get_default_generation_params()
            if isinstance(conn, dict):
                configured_models = conn.get("configured_models", [])
                conn_gen_params = conn.get("generation_params", get_default_generation_params())
                if isinstance(configured_models, list):
                    for model_config in configured_models:
                        if isinstance(model_config, dict) and "generation_params" not in model_config:
                            model_config["generation_params"] = copy.deepcopy(conn_gen_params)
        settings_data["custom_connections"] = conns
    else:
        settings_data["custom_connections"] = []

    conn_gen_params = settings_data.get("gemini_generation_params", {})
    global_enable_thinking = conn_gen_params.get("enable_model_thinking", True)

    for conn in settings_data.get("custom_connections", []):
        if isinstance(conn, dict):
            for model_config in conn.get("configured_models", []):
                if isinstance(model_config, dict):
                    tc = model_config.setdefault("thinking_config", {})
                    if "enabled" not in tc:
                        tc["enabled"] = global_enable_thinking
    params = settings_data.get("gemini_generation_params", {})
    if isinstance(params, dict):
        default_params = get_default_generation_params()
        default_params.update(params)
        settings_data["gemini_generation_params"] = default_params
    else:
        settings_data["gemini_generation_params"] = get_default_generation_params()
    if not isinstance(settings_data.get("recent_files"), list):
        settings_data["recent_files"] = []
    settings_data["recent_files"] = [
        f for f in settings_data["recent_files"] if isinstance(f, str) and f
    ][:MAX_RECENT_FILES]
    for lang_key, default_list in [
        ("target_languages", []),
        ("available_source_languages", ["English"]),
    ]:
        if not isinstance(settings_data.get(lang_key), list):
            settings_data[lang_key] = default_list
        current_list = settings_data.get(lang_key, [])
        settings_data[lang_key] = [str(lang) for lang in current_list if lang]
        if not settings_data[lang_key] and default_list:
            settings_data[lang_key] = default_list
    if (
        not settings_data.get("selected_source_language")
        or settings_data["selected_source_language"]
        not in settings_data["available_source_languages"]
    ):
        settings_data["selected_source_language"] = settings_data[
            "available_source_languages"
        ][0]
    if "selected_target_language" not in settings_data:
        settings_data["selected_target_language"] = ""
    if not settings_data.get("gemini_model"):
        settings_data["gemini_model"] = default_global_settings["gemini_model"]
    if not isinstance(settings_data.get("available_gemini_models"), list):
        settings_data["available_gemini_models"] = []
    settings_data["available_gemini_models"] = [
        str(model) for model in settings_data["available_gemini_models"] if model
    ]
    if "active_model_for_connection" not in settings_data or not isinstance(
        settings_data["active_model_for_connection"], dict
    ):
        settings_data["active_model_for_connection"] = {}
    if not isinstance(settings_data.get("proxy_custom_list"), list):
        settings_data["proxy_custom_list"] = []

    valid_proxies = []
    for p in settings_data["proxy_custom_list"]:
        if isinstance(p, dict) and p.get("host") and p.get("port"):
            valid_proxies.append({
                "protocol": p.get("protocol", "http"),
                "host": str(p["host"]),
                "port": int(p["port"]),
                "username": str(p.get("username", "")),
                "password": str(p.get("password", "")),
            })
    settings_data["proxy_custom_list"] = valid_proxies

    if "notifications" not in settings_data or not isinstance(settings_data.get("notifications"), dict):
        settings_data["notifications"] = copy.deepcopy(default_global_settings["notifications"])
    else:
        notif_defaults = default_global_settings["notifications"]
        for key, default_val in notif_defaults.items():
            if key not in settings_data["notifications"]:
                settings_data["notifications"][key] = copy.deepcopy(default_val)


def _atomic_write_yaml(path: str, data, yaml: YAML) -> None:
    """Write YAML through a temp file so a crash cannot truncate the real file."""
    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _migrate_old_json_settings(yaml):
    """Миграция со старого JSON файла настроек."""
    logger.info("Old 'translator_settings.json' found. Starting migration...")
    try:
        with open(OLD_SETTINGS_JSON_FILE, "r", encoding="utf-8") as f:
            old_data = json.load(f)
        migrated_data = _migrate_settings(old_data)
        connections = migrated_data.pop("custom_connections", [])
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        os.makedirs(CONNECTIONS_DIR, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            yaml.dump(migrated_data, f)
        logger.info(f"Migrated main settings to '{SETTINGS_FILE}'")
        for conn in connections:
            conn_id = conn.get("id")
            if not conn_id:
                logger.warning(
                    f"Skipping migration for a connection without an ID: {conn.get('name')}"
                )
                continue
            conn_path = os.path.join(CONNECTIONS_DIR, f"{conn_id}.yaml")
            with open(conn_path, "w", encoding="utf-8") as f:
                yaml.dump(conn, f)
        logger.info(f"Migrated {len(connections)} connections to '{CONNECTIONS_DIR}'")
        backup_path = OLD_SETTINGS_JSON_FILE + ".bak"
        shutil.move(OLD_SETTINGS_JSON_FILE, backup_path)
        logger.info(
            f"Successfully migrated settings. Old file renamed to '{os.path.basename(backup_path)}'."
        )
        return True
    except Exception as e:
        logger.error(f"Migration from old settings file failed: {e}", exc_info=True)
        return False


def _migrate_to_new_structure(yaml):
    """Миграция со старой структуры (settings/app_settings.yaml) на новую (settings/global/ + settings/{app_id}/)."""
    old_settings_file = SETTINGS_FILE  # settings/app_settings.yaml
    old_connections_dir = CONNECTIONS_DIR  # settings/connections/
    old_notif_history = os.path.join(SETTINGS_DIR, "notifications_history.json")

    # Проверяем, нужна ли миграция
    if not os.path.exists(old_settings_file):
        return  # Старого файла нет - миграция не нужна

    if os.path.exists(GLOBAL_SETTINGS_FILE):
        return  # Новая структура уже существует

    logger.info("Migrating settings to new structure (global/ + app/)...")

    try:
        # Создаём новую структуру папок
        os.makedirs(GLOBAL_SETTINGS_DIR, exist_ok=True)
        os.makedirs(GLOBAL_CONNECTIONS_DIR, exist_ok=True)
        if APP_SETTINGS_DIR:
            os.makedirs(APP_SETTINGS_DIR, exist_ok=True)

        # Загружаем старые настройки
        with open(old_settings_file, 'r', encoding='utf-8') as f:
            old_settings = yaml.load(f) or {}

        # Разделяем на общие и индивидуальные
        global_settings_data = {}
        app_settings_data = {}

        # Ключи, которые относятся к глобальным настройкам
        global_keys = set(default_global_settings.keys())
        global_keys.add("custom_connections")  # custom_connections тоже глобальная

        for key, value in old_settings.items():
            if key in global_keys:
                global_settings_data[key] = value
            elif key in default_app_settings:
                app_settings_data[key] = value
            else:
                # Неизвестный ключ - добавляем в глобальные для сохранности
                logger.warning(f"Unknown setting key '{key}' - adding to global settings")
                global_settings_data[key] = value

        if app_settings_data and not APP_SETTINGS_FILE:
            logger.error(
                "Cannot migrate app settings: app_id is not resolved. "
                "Migration aborted to avoid losing %d app keys.",
                len(app_settings_data),
            )
            return

        # Сохраняем глобальные настройки
        _atomic_write_yaml(GLOBAL_SETTINGS_FILE, global_settings_data, yaml)
        logger.info(f"Saved global settings to '{GLOBAL_SETTINGS_FILE}'")

        # Сохраняем настройки приложения (если есть app_id и данные)
        if APP_SETTINGS_FILE and app_settings_data:
            _atomic_write_yaml(APP_SETTINGS_FILE, app_settings_data, yaml)
            logger.info(f"Saved app settings to '{APP_SETTINGS_FILE}'")

        # Переносим соединения
        if os.path.exists(old_connections_dir):
            for conn_file in os.listdir(old_connections_dir):
                if conn_file.endswith(('.yaml', '.yml')):
                    src_path = os.path.join(old_connections_dir, conn_file)
                    dst_path = os.path.join(GLOBAL_CONNECTIONS_DIR, conn_file)
                    shutil.move(src_path, dst_path)
                    logger.debug(f"Moved connection: {conn_file}")

        # Переносим историю уведомлений
        if os.path.exists(old_notif_history):
            shutil.move(old_notif_history, NOTIFICATIONS_HISTORY_FILE)
            logger.info(f"Moved notifications history to '{NOTIFICATIONS_HISTORY_FILE}'")

        # Создаём .bak старого файла
        backup_path = old_settings_file + ".bak"
        shutil.move(old_settings_file, backup_path)
        logger.info(f"Old settings file renamed to '{os.path.basename(backup_path)}'")

        # Удаляем старую папку connections если она пуста
        try:
            if os.path.exists(old_connections_dir) and not os.listdir(old_connections_dir):
                os.rmdir(old_connections_dir)
                logger.debug(f"Removed empty directory: {old_connections_dir}")
        except Exception:
            pass

        logger.info("Migration to new structure completed successfully")

    except Exception as e:
        logger.error(f"Failed to migrate to new structure: {e}", exc_info=True)
        raise


def load_global_settings():
    """Загружает общие настройки из global/app_settings.yaml."""
    global _global_settings

    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.preserve_quotes = True

    _global_settings = copy.deepcopy(default_global_settings)

    if os.path.exists(GLOBAL_SETTINGS_FILE):
        try:
            with open(GLOBAL_SETTINGS_FILE, "r", encoding="utf-8") as f:
                loaded_data = yaml.load(f) or {}
            logger.info(f"Loaded global settings from {GLOBAL_SETTINGS_FILE}")

            for key, value in loaded_data.items():
                if key in default_global_settings or key == "custom_connections":
                    _global_settings[key] = value
        except Exception as e:
            logger.error(
                f"Failed to load global settings file, using defaults. Error: {e}",
                exc_info=True,
            )

    # Загружаем соединения из global/connections/
    loaded_connections = []
    if os.path.exists(GLOBAL_CONNECTIONS_DIR):
        try:
            for filename in os.listdir(GLOBAL_CONNECTIONS_DIR):
                if filename.endswith((".yaml", ".yml")):
                    file_path = os.path.join(GLOBAL_CONNECTIONS_DIR, filename)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            conn_data = yaml.load(f)
                        if isinstance(conn_data, dict) and conn_data.get("id"):
                            loaded_connections.append(conn_data)
                        else:
                            logger.warning(f"Skipping invalid connection file: {filename}")
                    except Exception as e:
                        logger.error(f"Failed to load connection file '{filename}': {e}")
        except Exception as e:
            logger.error(f"Failed to scan connections directory: {e}")

    _global_settings["custom_connections"] = loaded_connections
    logger.info(f"Loaded {len(loaded_connections)} custom connections.")


def load_app_settings():
    """Загружает индивидуальные настройки приложения."""
    global _app_settings

    _app_settings = copy.deepcopy(default_app_settings)

    if not APP_SETTINGS_FILE:
        logger.warning(
            "APP_SETTINGS_FILE is not set: app settings will use defaults and will not be saved."
        )
        return

    if not os.path.exists(APP_SETTINGS_FILE):
        logger.info("No app-specific settings file, using defaults")
        return

    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.preserve_quotes = True

    try:
        with open(APP_SETTINGS_FILE, "r", encoding="utf-8") as f:
            loaded_data = yaml.load(f) or {}
        logger.info(f"Loaded app settings from {APP_SETTINGS_FILE}")

        for key, value in loaded_data.items():
            if key in default_app_settings:
                _app_settings[key] = value
    except Exception as e:
        logger.error(
            f"Failed to load app settings file, using defaults. Error: {e}",
            exc_info=True,
        )


def load_settings():
    """Главная функция - загружает оба типа настроек и объединяет их."""
    global current_settings

    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.preserve_quotes = True

    # Миграция со старого JSON (если есть)
    if os.path.exists(OLD_SETTINGS_JSON_FILE):
        _migrate_old_json_settings(yaml)

    # Миграция на новую структуру (если нужно)
    _migrate_to_new_structure(yaml)

    # Создаём папки если их нет
    os.makedirs(GLOBAL_SETTINGS_DIR, exist_ok=True)
    os.makedirs(GLOBAL_CONNECTIONS_DIR, exist_ok=True)
    if APP_SETTINGS_DIR:
        os.makedirs(APP_SETTINGS_DIR, exist_ok=True)

    # Загружаем настройки
    load_global_settings()
    load_app_settings()

    # Объединяем в current_settings
    current_settings = {}
    current_settings.update(_global_settings)
    current_settings.update(_app_settings)

    # Legacy Gemini settings become a normal connection profile.
    from .gemini_migration import migrate_legacy_gemini_settings

    if migrate_legacy_gemini_settings(current_settings):
        logger.info("Migrated legacy Gemini settings into a 'Google Gemini' connection.")

    # Устанавливаем версию ядра
    current_settings["CORE_VERSION"] = CORE_VERSION

    # Валидация
    _validate_and_clean_settings(current_settings)

    # Настройка прокси-менеджера
    proxy_manager.configure(
        enabled=current_settings.get("proxy_enabled", False),
        custom_proxies=current_settings.get("proxy_custom_list", []),
    )


def save_global_settings():
    """Сохраняет общие настройки."""
    global _global_settings

    if not _global_settings:
        return

    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.preserve_quotes = True

    os.makedirs(GLOBAL_SETTINGS_DIR, exist_ok=True)
    os.makedirs(GLOBAL_CONNECTIONS_DIR, exist_ok=True)

    try:
        # Копируем глобальные настройки
        settings_to_save = copy.deepcopy(_global_settings)

        # Извлекаем соединения для отдельного сохранения
        connections = settings_to_save.pop("custom_connections", [])

        # Валидация индекса API ключа
        num_keys = len(settings_to_save.get("api_keys", []))
        if not (0 <= settings_to_save.get("current_api_key_index", 0) < num_keys):
            settings_to_save["current_api_key_index"] = 0

        # Сохраняем основные настройки
        _atomic_write_yaml(GLOBAL_SETTINGS_FILE, settings_to_save, yaml)

        # Управление файлами соединений
        current_conn_ids = {conn["id"] for conn in connections if "id" in conn}
        existing_files = {
            f for f in os.listdir(GLOBAL_CONNECTIONS_DIR) if f.endswith((".yaml", ".yml"))
        }
        existing_ids = {os.path.splitext(f)[0] for f in existing_files}
        ids_to_delete = existing_ids - current_conn_ids

        for conn_id in ids_to_delete:
            file_path = os.path.join(GLOBAL_CONNECTIONS_DIR, f"{conn_id}.yaml")
            try:
                os.remove(file_path)
                logger.debug(f"Removed obsolete connection file: {file_path}")
            except OSError as e:
                logger.error(f"Failed to remove obsolete connection file {file_path}: {e}")

        for conn in connections:
            conn_id = conn.get("id")
            if not conn_id:
                continue
            file_path = os.path.join(GLOBAL_CONNECTIONS_DIR, f"{conn_id}.yaml")
            _atomic_write_yaml(file_path, conn, yaml)

        logger.info("Global settings and connections saved.")

    except Exception as e:
        logger.error(f"Failed to save global settings: {e}")


def save_app_settings():
    """Сохраняет индивидуальные настройки приложения."""
    global _app_settings

    if not APP_SETTINGS_FILE:
        logger.warning("APP_SETTINGS_FILE is not set: app settings were not saved.")
        return

    if not _app_settings:
        return

    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.preserve_quotes = True

    os.makedirs(APP_SETTINGS_DIR, exist_ok=True)

    try:
        _atomic_write_yaml(APP_SETTINGS_FILE, _app_settings, yaml)
        logger.info(f"App settings saved to {APP_SETTINGS_FILE}")
    except Exception as e:
        logger.error(f"Failed to save app settings: {e}")


def save_settings():
    """Сохраняет все настройки, распределяя их по соответствующим файлам."""
    global _global_settings, _app_settings

    # Обновляем _global_settings из current_settings
    for key in default_global_settings.keys():
        if key in current_settings:
            _global_settings[key] = current_settings[key]

    # custom_connections тоже глобальная
    if "custom_connections" in current_settings:
        _global_settings["custom_connections"] = current_settings["custom_connections"]

    # Обновляем _app_settings из current_settings
    for key in default_app_settings.keys():
        if key in current_settings:
            _app_settings[key] = current_settings[key]

    # Session-only keys (ux_t_count, ux_next_prompt, ux_dialog_shown,
    # translation_mode_enabled, active_connections_list) are intentionally
    # not persisted: they reset every launch.
    # Сохраняем
    save_global_settings()
    save_app_settings()


def get_notifications_history_path() -> str:
    """Возвращает путь к файлу истории уведомлений."""
    return NOTIFICATIONS_HISTORY_FILE


def get_global_connections_dir() -> str:
    """Возвращает путь к папке с соединениями."""
    return GLOBAL_CONNECTIONS_DIR

