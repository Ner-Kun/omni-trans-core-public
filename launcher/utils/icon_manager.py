import requests
from PySide6.QtGui import QIcon
from launcher import config
from rich.console import Console

console = Console()


class IconManager:
    @staticmethod
    def get_icon_path(name: str) -> str:
        data = config.SOCIAL_CONFIG.get(name)
        if not data:
            return ""

        extension = data["icon_ext"]
        url = data["icon_url"]

        file_path = config.ICONS_DIR / f"{name}{extension}"

        if file_path.exists():
            return str(file_path)

        try:
            console.log(f"Downloading {name} ({extension})...")
            response = requests.get(url, timeout=5)
            response.raise_for_status()

            with open(file_path, "wb") as f:
                f.write(response.content)

            return str(file_path)
        except Exception as e:
            console.log(f"Failed to download {name}: {e}")
            return ""

    @staticmethod
    def get_qicon(name: str) -> QIcon:
        path = IconManager.get_icon_path(name)
        if path:
            return QIcon(path)
        return QIcon()
