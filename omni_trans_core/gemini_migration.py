import copy
import logging
from typing import Any

from .constants import PROVIDER_DEFAULT_TIMEOUT

logger = logging.getLogger("CORE.gemini_migration")

GEMINI_CONNECTION_ID = "conn_legacy_gemini"
GEMINI_CONNECTION_NAME = "Google Gemini"
GEMINI_PROVIDER_ID = "gemini"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def _mask_key(api_key: str) -> str:
    return f"{api_key[:3]}...{api_key[-4:]}" if len(api_key) > 7 else "****"


def _clean_api_keys(raw_keys: Any) -> list[str]:
    if not isinstance(raw_keys, list):
        return []
    api_keys: list[str] = []
    for raw_key in raw_keys:
        if not isinstance(raw_key, str):
            continue
        api_key = raw_key.strip()
        if api_key and api_key not in api_keys:
            api_keys.append(api_key)
    return api_keys


def _is_gemini_connection(connection: Any) -> bool:
    if not isinstance(connection, dict):
        return False
    return (
        connection.get("name") == GEMINI_CONNECTION_NAME
        or connection.get("provider") == GEMINI_PROVIDER_ID
    )


def _resolve_model_id(settings_data: dict[str, Any]) -> str:
    model_id = settings_data.get("gemini_model")
    if isinstance(model_id, str) and model_id.strip():
        return model_id.strip()
    return DEFAULT_GEMINI_MODEL


def _resolve_rpm(settings_data: dict[str, Any]) -> int | None:
    rpm_limit = settings_data.get("rpm_limit")
    if isinstance(rpm_limit, bool) or not isinstance(rpm_limit, int):
        return None
    return rpm_limit if rpm_limit > 0 else None


def _build_gemini_connection(
    settings_data: dict[str, Any], api_keys: list[str], model_id: str
) -> dict[str, Any]:
    raw_params = settings_data.get("gemini_generation_params")
    generation_params = copy.deepcopy(raw_params) if isinstance(raw_params, dict) else {}
    return {
        "id": GEMINI_CONNECTION_ID,
        "name": GEMINI_CONNECTION_NAME,
        "provider": GEMINI_PROVIDER_ID,
        "api_key": api_keys[0],
        "api_keys": list(api_keys),
        "base_url": "",
        "timeout": PROVIDER_DEFAULT_TIMEOUT,
        # The legacy Gemini strategy dispatched jobs in parallel whenever a key
        # was free; waiting for each response would drop throughput to one job.
        "wait_for_response": False,
        "global_limits": {
            "rpm": _resolve_rpm(settings_data),
            "rpd": None,
            "tpm": None,
        },
        "headers": {},
        "configured_models": [
            {
                "model_id": model_id,
                "parsing_rules": {"start_tag": "", "end_tag": ""},
                "limits": {
                    "use_global_limits": True,
                    "rpm": None,
                    "rpd": None,
                    "tpm": None,
                },
                "thinking_config": {
                    "mode": "auto",
                    "enabled": generation_params.get("enable_model_thinking", True),
                    "enable_cmd": "",
                    "disable_cmd": "",
                },
                "additional_params": {
                    "include_body_params": "",
                    "exclude_body_params": "",
                    "include_headers": "",
                },
                "generation_params": copy.deepcopy(generation_params),
            }
        ],
        "generation_params": copy.deepcopy(generation_params),
    }


def migrate_legacy_gemini_settings(settings_data: dict[str, Any]) -> bool:
    """Create a Google Gemini connection from legacy top-level keys.

    Returns True if a connection was created, False if there was nothing
    to migrate or a Gemini connection already exists.
    """
    api_keys = _clean_api_keys(settings_data.get("api_keys"))
    if not api_keys:
        logger.debug("No legacy Gemini API keys found, nothing to migrate.")
        return False

    connections = settings_data.get("custom_connections")
    if not isinstance(connections, list):
        connections = []
        settings_data["custom_connections"] = connections
    elif any(_is_gemini_connection(conn) for conn in connections):
        logger.debug("A Gemini connection already exists, migration skipped.")
        return False

    model_id = _resolve_model_id(settings_data)
    connections.append(_build_gemini_connection(settings_data, api_keys, model_id))

    active_models = settings_data.get("active_model_for_connection")
    if not isinstance(active_models, dict):
        active_models = {}
        settings_data["active_model_for_connection"] = active_models
    active_models[GEMINI_CONNECTION_NAME] = model_id

    logger.info(
        "Created '%s' connection from legacy settings with %d key(s): %s",
        GEMINI_CONNECTION_NAME,
        len(api_keys),
        ", ".join(_mask_key(api_key) for api_key in api_keys),
    )
    return True
