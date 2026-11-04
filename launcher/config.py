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
STYLES_QSS = RESOURCES_DIR / "styles.qss"
UPDATER_TEMPLATE = RESOURCES_DIR / "updater.bat"

if sys.platform == "win32":
    VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
else:
    VENV_PYTHON = VENV_DIR / "bin" / "python"

MANIFEST_URL = ("https://raw.githubusercontent.com/Ner-Kun/omni-trans-launcher/main/manifest.json")
URL_LAUNCHER_REQ = "https://raw.githubusercontent.com/Ner-Kun/omni-trans-launcher/refs/heads/main/requirements.txt"
URL_CORE_REQ = "https://raw.githubusercontent.com/Ner-Kun/omni-trans-core/refs/heads/main/requirements.txt"
UV_DOWNLOAD_URL = "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"

SOCIAL_CONFIG = {
    "telegram": {
        "link": "https://t.me/ner_kun_off",
        "icon_url": "https://cdn.simpleicons.org/telegram/e0e0e0",
        "icon_ext": ".svg",
    },
    "github": {
        "link": "https://github.com/Ner-Kun/omni-trans-launcher",
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


LAUNCHER_VERSION = "1.0.0"
ANIMATION_PAUSE_MS = 1000

for path in [TEMP_DIR, DATA_DIR, RESOURCES_DIR, TOOL_DIR]:
    path.mkdir(parents=True, exist_ok=True)
