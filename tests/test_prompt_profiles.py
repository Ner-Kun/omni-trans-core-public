"""Tests for prompt profile storage, defaults and scope migration.

Paths come from ``tmp_path`` only: the manager reads its directory from
``settings`` when it is not told explicitly, so the relevant settings globals
are patched for every test and restored by monkeypatch.
"""
from pathlib import Path

import pytest

from omni_trans_core import prompt_profile, settings
from omni_trans_core.prompt_profile import PromptProfile
from omni_trans_core.prompt_profile_manager import PromptProfileManager


@pytest.fixture(autouse=True)
def isolated_prompt_paths(monkeypatch):
    """Keep the manager away from the real project prompt directories."""
    monkeypatch.setattr(settings, "GLOBAL_PROMPTS_DIR", "")
    monkeypatch.setattr(settings, "APP_PROMPTS_DIR", "")
    monkeypatch.setattr(settings, "CURRENT_APP_ID", "")


def make_custom_default(name="App Default"):
    return PromptProfile(
        profile_name=name,
        profile_description="Default supplied by the application",
        version="1.0",
        system_prompt=(
            "You translate {source_language_name} terms into "
            "{target_language_name} for a game lorebook.\n\n{context_instructions}"
        ),
        user_prompt='Lorebook term: "{keyword}"\nTranslation:',
        regen_prompt=(
            'The term "{keyword}" was translated as "{wrong_keyword}".\n'
            "Give a better {target_language_name} translation:"
        ),
        context_instructions="<context>\n{context_section}\n</context>",
    )


def profile_path(directory, profile_name):
    return Path(directory) / f"{profile_name.lower().replace(' ', '_')}.md"


def test_load_profiles_creates_custom_default(tmp_path):
    prompts_dir = tmp_path / "prompts"
    custom = make_custom_default()

    manager = PromptProfileManager(
        profiles_dir=str(prompts_dir), default_profile=custom
    )
    profiles = manager.load_profiles()

    assert [p.profile_name for p in profiles] == [custom.profile_name]
    created = profile_path(prompts_dir, custom.profile_name)
    assert created.exists()
    assert f"profile_name: {custom.profile_name}" in created.read_text(encoding="utf-8")


def test_get_default_profile_does_not_overwrite_existing_file(tmp_path):
    prompts_dir = tmp_path / "prompts"
    custom = make_custom_default()

    first = PromptProfileManager(profiles_dir=str(prompts_dir), default_profile=custom)
    first.load_profiles()

    path = profile_path(prompts_dir, custom.profile_name)
    edited = custom.copy()
    edited.profile_description = "edited on disk"
    path.write_text(edited.to_markdown(), encoding="utf-8")

    # Fresh manager: empty cache, so the profile has to come from disk.
    second = PromptProfileManager(
        profiles_dir=str(prompts_dir), default_profile=make_custom_default()
    )
    resolved = second.get_default_profile()

    assert resolved.profile_name == custom.profile_name
    assert resolved.profile_description == "edited on disk"
    assert "edited on disk" in path.read_text(encoding="utf-8")


def test_create_profile_starts_from_custom_default(tmp_path):
    prompts_dir = tmp_path / "prompts"
    custom = make_custom_default()

    manager = PromptProfileManager(
        profiles_dir=str(prompts_dir), default_profile=custom
    )
    manager.load_profiles()
    created = manager.create_profile("My Profile", "derived from app default")

    neutral = prompt_profile.get_default_profile()
    assert created.system_prompt == custom.system_prompt
    assert created.user_prompt == custom.user_prompt
    assert created.regen_prompt == custom.regen_prompt
    assert created.system_prompt != neutral.system_prompt


def test_delete_profile_refuses_to_remove_default(tmp_path):
    prompts_dir = tmp_path / "prompts"
    custom = make_custom_default()

    manager = PromptProfileManager(
        profiles_dir=str(prompts_dir), default_profile=custom
    )
    manager.load_profiles()

    assert manager.delete_profile(custom.profile_name) is False
    assert profile_path(prompts_dir, custom.profile_name).exists()


def test_global_profiles_are_copied_into_app_scope(tmp_path, monkeypatch):
    global_dir = tmp_path / "settings" / "global" / "prompts"
    app_dir = tmp_path / "settings" / "lgt_app" / "prompts"
    global_dir.mkdir(parents=True)
    app_dir.mkdir(parents=True)

    shared = make_custom_default("Shared")
    global_file = global_dir / "shared.md"
    global_file.write_text(shared.to_markdown(), encoding="utf-8")

    monkeypatch.setattr(settings, "GLOBAL_PROMPTS_DIR", str(global_dir))
    monkeypatch.setattr(settings, "APP_PROMPTS_DIR", str(app_dir))

    manager = PromptProfileManager(profiles_dir=None)

    assert Path(manager.profiles_dir) == app_dir
    assert (app_dir / "shared.md").exists()
    assert global_file.exists(), "migration must copy, not move"


def test_profiles_dir_defaults_to_app_scope(tmp_path, monkeypatch):
    app_dir = tmp_path / "settings" / "lgt_app" / "prompts"
    global_dir = tmp_path / "settings" / "global" / "prompts"

    monkeypatch.setattr(settings, "APP_PROMPTS_DIR", str(app_dir))
    monkeypatch.setattr(settings, "GLOBAL_PROMPTS_DIR", str(global_dir))

    manager = PromptProfileManager()

    assert manager.profiles_dir == settings.APP_PROMPTS_DIR
    assert Path(manager.profiles_dir) == app_dir
