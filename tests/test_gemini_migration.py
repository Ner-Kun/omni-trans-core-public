import copy

import pytest

from omni_trans_core.constants import PROVIDER_DEFAULT_TIMEOUT
from omni_trans_core.gemini_migration import migrate_legacy_gemini_settings

LEGACY_PARAMS = {
    "enable_model_thinking": False,
    "thinking_budget_value": -1,
    "temperature": 0.35,
    "top_p": 0.9,
    "max_output_tokens": 8000,
}


def _legacy_settings() -> dict:
    return {
        "api_keys": [
            "AIzaSy-legacy-key-one",
            " AIzaSy-legacy-key-two ",
            "AIzaSy-legacy-key-one",
            "",
            "   ",
        ],
        "gemini_model": "gemini-2.5-pro",
        "gemini_generation_params": copy.deepcopy(LEGACY_PARAMS),
        "rpm_limit": 30,
        "active_model_for_connection": {"Other Provider": "other-model"},
    }


def _connections(settings_data: dict) -> list[dict]:
    return settings_data["custom_connections"]


def _gemini_connection(settings_data: dict) -> dict:
    return next(
        conn
        for conn in _connections(settings_data)
        if conn.get("provider") == "gemini"
    )


@pytest.mark.parametrize(
    "settings_data",
    [
        {},
        {"api_keys": []},
        {"api_keys": None},
        {"api_keys": "single-string-key"},
        {"api_keys": ["", "   "]},
        {"api_keys": [1, 2, None]},
    ],
)
def test_no_api_keys_creates_nothing(settings_data):
    assert migrate_legacy_gemini_settings(settings_data) is False
    assert settings_data.get("custom_connections", []) == []
    assert "active_model_for_connection" not in settings_data


def test_migrates_legacy_gemini_settings():
    settings_data = _legacy_settings()

    assert migrate_legacy_gemini_settings(settings_data) is True

    assert len(_connections(settings_data)) == 1
    connection = _gemini_connection(settings_data)
    assert connection["id"] == "conn_legacy_gemini"
    assert connection["name"] == "Google Gemini"
    assert connection["provider"] == "gemini"
    assert connection["api_key"] == "AIzaSy-legacy-key-one"
    assert connection["api_keys"] == [
        "AIzaSy-legacy-key-one",
        "AIzaSy-legacy-key-two",
    ]
    assert connection["base_url"] == ""
    assert connection["headers"] == {}
    assert connection["timeout"] == PROVIDER_DEFAULT_TIMEOUT
    assert connection["global_limits"] == {"rpm": 30, "rpd": None, "tpm": None}
    assert connection["generation_params"] == LEGACY_PARAMS

    model = connection["configured_models"][0]
    assert model["model_id"] == "gemini-2.5-pro"
    assert model["generation_params"] == LEGACY_PARAMS
    assert model["thinking_config"] == {
        "mode": "auto",
        "enabled": False,
        "enable_cmd": "",
        "disable_cmd": "",
    }
    assert settings_data["active_model_for_connection"] == {
        "Other Provider": "other-model",
        "Google Gemini": "gemini-2.5-pro",
    }


def test_legacy_keys_are_kept_for_rollback():
    settings_data = _legacy_settings()
    original_keys = copy.deepcopy(settings_data["api_keys"])

    migrate_legacy_gemini_settings(settings_data)

    assert settings_data["api_keys"] == original_keys
    assert settings_data["gemini_model"] == "gemini-2.5-pro"
    assert settings_data["gemini_generation_params"] == LEGACY_PARAMS
    assert settings_data["rpm_limit"] == 30


def test_migration_is_idempotent():
    settings_data = _legacy_settings()

    assert migrate_legacy_gemini_settings(settings_data) is True
    assert migrate_legacy_gemini_settings(settings_data) is False

    assert len(_connections(settings_data)) == 1


def test_existing_gemini_connection_blocks_migration():
    settings_data = _legacy_settings()
    existing = {
        "id": "conn_existing",
        "name": "Gemini Work",
        "provider": "gemini",
        "api_key": "existing-key",
        "configured_models": [],
    }
    settings_data["custom_connections"] = [existing]

    assert migrate_legacy_gemini_settings(settings_data) is False
    assert _connections(settings_data) == [existing]


def test_existing_connection_with_same_name_blocks_migration():
    settings_data = _legacy_settings()
    existing = {
        "id": "conn_existing",
        "name": "Google Gemini",
        "provider": "openai",
        "api_key": "existing-key",
        "configured_models": [],
    }
    settings_data["custom_connections"] = [existing]

    assert migrate_legacy_gemini_settings(settings_data) is False
    assert _connections(settings_data) == [existing]


def test_generation_params_are_deep_copied():
    settings_data = _legacy_settings()

    migrate_legacy_gemini_settings(settings_data)

    connection = _gemini_connection(settings_data)
    model = connection["configured_models"][0]
    assert connection["generation_params"] is not settings_data["gemini_generation_params"]
    assert model["generation_params"] is not connection["generation_params"]

    connection["generation_params"]["temperature"] = 9.9
    model["generation_params"]["top_p"] = 0.1

    assert settings_data["gemini_generation_params"] == LEGACY_PARAMS
    assert connection["generation_params"]["top_p"] == 0.9


def test_missing_model_and_rpm_fall_back_to_defaults():
    settings_data = {
        "api_keys": ["AIzaSy-key"],
        "gemini_model": "",
        "gemini_generation_params": {},
        "rpm_limit": 0,
    }

    assert migrate_legacy_gemini_settings(settings_data) is True

    connection = _gemini_connection(settings_data)
    assert connection["configured_models"][0]["model_id"] == "gemini-2.5-flash"
    assert connection["global_limits"] == {"rpm": None, "rpd": None, "tpm": None}
    assert connection["configured_models"][0]["thinking_config"]["enabled"] is True
    assert settings_data["active_model_for_connection"] == {
        "Google Gemini": "gemini-2.5-flash"
    }
