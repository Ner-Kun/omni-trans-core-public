import os
import sys
from pathlib import Path

LAUNCHER_FILE = Path(__file__).resolve()

LAUNCHER_DIR = LAUNCHER_FILE.parent
ROOT_DIR = LAUNCHER_DIR.parent
APPS_DIR = ROOT_DIR
VENV_DIR = ROOT_DIR / ".venv"
TEMP_DIR = LAUNCHER_DIR / "temp"
DATA_DIR = LAUNCHER_DIR / "data"
RESOURCES_DIR = LAUNCHER_DIR / "resources"
TOOL_DIR = LAUNCHER_DIR / "tool"
ICONS_DIR = DATA_DIR / "icons"
ICONS_DIR.mkdir(parents=True, exist_ok=True)
UV_DIR = TOOL_DIR / "uv"
UV_EXEC = UV_DIR / "uv.exe"
UV_CACHE_DIR = TEMP_DIR / "uv_cache"

INSTALLED_APPS_JSON = DATA_DIR / "installed_apps.json"
LAUNCHER_SETTINGS_JSON = DATA_DIR / "settings.json"
UPDATER_TEMPLATE = RESOURCES_DIR / "updater.bat"

if sys.platform == "win32":
    VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
else:
    VENV_PYTHON = VENV_DIR / "bin" / "python"

APP_NAME = "Omni Trans Launcher"
LAUNCHER_VERSION = "1.2.0"

# Dev mode keeps the launcher on local requirements and a local manifest
# instead of pulling release data from GitHub.
DEV_MODE = os.environ.get("OMNI_LAUNCHER_DEV", "").strip() == "1"
LOCAL_MANIFEST = DATA_DIR / "manifest.dev.json"
LOCAL_LAUNCHER_REQUIREMENTS = LAUNCHER_DIR / "requirements.txt"
LOCAL_CORE_REQUIREMENTS = ROOT_DIR / "requirements.txt"

_DEFAULT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/Ner-Kun/omni-trans-core-public/main/manifest.json"
)
MANIFEST_URL = os.environ.get("OMNI_LAUNCHER_MANIFEST_URL", "").strip() or (
    str(LOCAL_MANIFEST)
    if DEV_MODE and LOCAL_MANIFEST.exists()
    else _DEFAULT_MANIFEST_URL
)
URL_LAUNCHER_REQ = (
    "https://raw.githubusercontent.com/Ner-Kun/omni-trans-core-public/refs/heads/main/launcher/requirements.txt"
)
URL_CORE_REQ = (
    "https://raw.githubusercontent.com/Ner-Kun/omni-trans-core-public/refs/heads/main/requirements.txt"
)
UV_DOWNLOAD_URL = (
    "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"
)

WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 720

SOCIAL_CONFIG = {
    "telegram": {
        "link": "https://t.me/ner_kun_off",
        "icon_url": "https://cdn.simpleicons.org/telegram/e0e0e0",
        "icon_ext": ".svg",
    },
    "github": {
        "link": "https://github.com/Ner-Kun/omni-trans-core-public",
        "icon_url": "https://cdn.simpleicons.org/github/e0e0e0",
        "icon_ext": ".svg",
    },
    "donate": {
        "link_ua": "https://nerkun.donatik.ua/",
        "link_global": "https://1/",
        "icon_url": "https://cdn.simpleicons.org/githubsponsors/e0e0e0",
        "icon_ext": ".svg",
    },
}

NAG_CONFIG = {
    "launcher": {
        "milestones": [5, 10, 15],
        "loop_start": 15,
        "loop_step": 10,
    },
    "app": {
        "milestones": [10, 20],
        "loop_start": 20,
        "loop_step": 10,
    },
}

ANIMATION_PAUSE_MS = 1000

for path in [TEMP_DIR, DATA_DIR, RESOURCES_DIR, TOOL_DIR]:
    path.mkdir(parents=True, exist_ok=True)
