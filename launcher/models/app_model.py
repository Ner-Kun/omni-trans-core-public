from dataclasses import dataclass, field
from PySide6.QtGui import QIcon


@dataclass
class AppData:
    """Data model for an application entry in the catalog."""

    folder_name: str = ""
    name: str = "Unknown"
    description: str = ""
    local_version: str = "0.0.0"
    latest_version: str = "0.0.0"
    is_local: bool = False
    update_available: bool = False
    is_running: bool = False
    is_launching: bool = False
    is_critical: bool = False
    changelog: str = ""
    repo_url: str = ""
    min_core_version: str = "0.0.0"
    exe_path: str = "runner.py"
    icon: QIcon = field(default_factory=QIcon)
    raw_data: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict, local_data: dict | None = None) -> "AppData":
        folder = data.get("folder_name", data.get("id", ""))
        local_version = data.get("local_version", "0.0.0")
        is_local = data.get("is_local", False)
        update_available = data.get("update_available", False)
        is_critical = data.get("critical", False)
        changelog = ""

        if local_data:
            is_local = True
            local_version = local_data.get("version", "0.0.0")

            if local_data.get("pending_update_version"):
                update_available = True
                changelog = local_data.get("pending_changelog", "")
                is_critical = local_data.get("is_critical", False)
            else:
                changelog = local_data.get("changelog", "")
        elif update_available:
            changelog = data.get("changelog", "")
            is_critical = data.get("critical", False)

        latest_version = data.get("version", local_version)
        if data.get("latest_version"):
            latest_version = data["latest_version"]
        elif local_data and local_data.get("pending_update_version"):
            latest_version = local_data["pending_update_version"]

        return cls(
            folder_name=folder,
            name=data.get("name", "Unknown"),
            description=data.get("description", local_data.get("description", "") if local_data else ""),
            local_version=local_version,
            latest_version=latest_version,
            is_local=is_local,
            update_available=update_available,
            is_running=data.get("is_running", False),
            is_launching=data.get("is_launching", False),
            is_critical=is_critical,
            changelog=changelog or data.get("changelog", ""),
            repo_url=data.get("repo_url", local_data.get("repo_url", "") if local_data else ""),
            min_core_version=data.get("min_core_version", "0.0.0"),
            exe_path=(
                local_data.get("exe_path", data.get("exe_path", "runner.py"))
                if local_data
                else data.get("exe_path", "runner.py")
            ),
            raw_data=data,
        )

    def to_dict(self) -> dict:
        return {
            "folder_name": self.folder_name,
            "name": self.name,
            "description": self.description,
            "version": self.local_version,
            "latest_version": self.latest_version,
            "is_local": self.is_local,
            "update_available": self.update_available,
            "is_running": self.is_running,
            "is_launching": self.is_launching,
            "is_critical": self.is_critical,
            "changelog": self.changelog,
            "repo_url": self.repo_url,
            "min_core_version": self.min_core_version,
            "exe_path": self.exe_path,
            "archive_name": self.raw_data.get("archive_name"),
            "branch": self.raw_data.get("branch", "main"),
        }