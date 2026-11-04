import base64
import shutil
import requests
import json
import zipfile
import io
import os
import re
import subprocess
import sys

from pathlib import Path
from datetime import datetime
from PySide6.QtGui import QPixmap, QIcon
from packaging.version import parse as parse_version
from rich.console import Console

from launcher import config
from launcher.utils.update_manager import UpdateManager, UpdateInfo
from launcher.utils.uv_manager import UvManager

console = Console()
DEFAULT_ICON_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="


class AppManager:
    def __init__(self):
        console.log("AppManager initialized.")
        self.update_manager = UpdateManager(config.APPS_DIR, config.MANIFEST_URL)
        self.uv_manager = UvManager()

    def get_catalog(self):
        console.log("Catalog Synchronization...")

        self.scan_local_apps()
        local_registry = self._load_installed_apps_cache()

        is_online = self.update_manager.fetch_manifest()
        remote_data = self.update_manager.manifest_data

        registry_dirty = False

        if is_online:
            console.log("Processing Metadata...")
            remote_apps = remote_data.get("apps", [])
            remote_map = {
                app.get("folder_name", app.get("id")): app for app in remote_apps
            }

            if "core" in remote_data:
                remote_map["omni_trans_core"] = remote_data["core"]
                remote_map["omni_trans_core"]["id"] = "core"

            if "launcher" in remote_data:
                remote_map["launcher"] = remote_data["launcher"]

            for folder, local_data in local_registry.items():
                if folder in remote_map:
                    remote_app = remote_map[folder]
                    remote_ver = remote_app.get("version", "0.0.0")
                    is_remote_critical = remote_app.get("critical", False)
                    last_known_critical = local_data.get(
                        "last_known_critical_version", "0.0.0"
                    )

                    if is_remote_critical and parse_version(remote_ver) > parse_version(
                        last_known_critical
                    ):
                        local_data["last_known_critical_version"] = remote_ver
                        console.log(
                            f"[Criticality] Updated barrier for {folder}: {last_known_critical} -> {remote_ver}"
                        )
                        registry_dirty = True

                    local_data["description"] = remote_app.get(
                        "description", local_data.get("description", "")
                    )
                    local_data["repo_url"] = remote_app.get(
                        "repo_url", local_data.get("repo_url", "")
                    )
                    local_data["min_core_version"] = remote_app.get(
                        "min_core_version", "0.0.0"
                    )
                    if remote_app.get("icon_base64"):
                        local_data["icon_base64"] = remote_app.get("icon_base64")

                    if not local_data.get("changelog"):
                        console.log(f"Missing changelog for {folder}. Fetching now...")
                        current_ver = local_data.get("version", "0.0.0")
                        repo = local_data.get("repo_url")

                        notes = self.update_manager.fetch_github_release_notes(
                            repo, current_ver
                        )
                        if notes:
                            local_data["changelog"] = notes
                            console.log(f"Updated changelog for {folder} locally.")
                            registry_dirty = True

            updates_list = self.update_manager.check_updates(local_registry)

            for app_key in local_registry:
                if "pending_update_version" in local_registry[app_key]:
                    del local_registry[app_key]["pending_update_version"]
                if "pending_changelog" in local_registry[app_key]:
                    del local_registry[app_key]["pending_changelog"]
                local_registry[app_key]["is_critical"] = False

            for update in updates_list:
                comp_id = update.component_id
                if comp_id in local_registry:
                    console.log(f"Caching NEW update info for {comp_id}")
                    local_registry[comp_id]["pending_update_version"] = (
                        update.remote_version
                    )
                    local_registry[comp_id]["pending_changelog"] = update.changelog
                    local_registry[comp_id]["pending_download_url"] = (
                        update.download_url
                    )

                    local_ver = local_registry[comp_id].get("version", "0.0.0")
                    barrier_ver = local_registry[comp_id].get(
                        "last_known_critical_version", "0.0.0"
                    )

                    if parse_version(local_ver) < parse_version(barrier_ver):
                        local_registry[comp_id]["is_critical"] = True
                        console.log(
                            f"{comp_id} marked CRITICAL (Local {local_ver} < Barrier {barrier_ver})"
                        )
                    else:
                        local_registry[comp_id]["is_critical"] = update.is_critical
                    registry_dirty = True

            if registry_dirty:
                self._save_installed_apps_cache(local_registry)

        full_catalog = []
        processed_ids = set()

        if is_online:
            for app in remote_data.get("apps", []):
                folder = app.get("folder_name", app.get("id"))
                processed_ids.add(folder)

                item = app.copy()
                item["folder_name"] = folder

                local_data = local_registry.get(folder)
                item["is_local"] = local_data is not None

                if local_data:
                    item["local_version"] = local_data.get("version", "0.0.0")
                    item["description"] = local_data.get("description", "")

                    if local_data.get("pending_update_version"):
                        item["update_available"] = True
                        item["latest_version"] = local_data["pending_update_version"]
                        item["changelog"] = local_data.get("pending_changelog", "")
                        item["critical"] = local_data.get("is_critical", False)
                    else:
                        item["update_available"] = False
                        item["changelog"] = local_data.get("changelog", "")
                else:
                    item["local_version"] = "0.0.0"
                    item["update_available"] = False

                full_catalog.append(item)

        for folder, data in local_registry.items():
            if folder in processed_ids or data.get("type") in ("core", "launcher"):
                continue

            item = data.copy()
            item["folder_name"] = folder
            item["is_local"] = True
            item["local_version"] = data.get("version", "0.0.0")
            item["update_available"] = False
            full_catalog.append(item)

        console.log(f"[green]Success[/] Catalog ready: {len(full_catalog)} items.")
        return full_catalog, is_online

    def scan_local_apps(self):
        console.log("Scanning disk for installed apps...")
        registry = self._load_installed_apps_cache()
        disk_folders = set()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        launcher_key = "launcher"
        disk_folders.add(launcher_key)
        if launcher_key not in registry:
            registry[launcher_key] = {
                "type": "launcher",
                "name": "Omni Trans Launcher",
                "version": config.LAUNCHER_VERSION,
                "install_date": current_time,
                "last_updated": current_time,
                "branch": "main",
            }
        else:
            if registry[launcher_key].get("version") != config.LAUNCHER_VERSION:
                registry[launcher_key]["version"] = config.LAUNCHER_VERSION
                registry[launcher_key]["last_updated"] = current_time

        core_dir = config.APPS_DIR / "omni_trans_core"
        if core_dir.exists():
            disk_folders.add("omni_trans_core")
            core_info = self._parse_app_info(core_dir, is_core=True)
            if core_info:
                if "omni_trans_core" not in registry:
                    registry["omni_trans_core"] = {
                        "type": "core",
                        "name": "Omni Trans Core",
                        "version": core_info["version"],
                        "install_date": current_time,
                        "last_updated": current_time,
                        "branch": "main",
                    }
                elif registry["omni_trans_core"].get("version") != core_info["version"]:
                    registry["omni_trans_core"]["version"] = core_info["version"]
                    registry["omni_trans_core"]["last_updated"] = current_time

        for item in config.APPS_DIR.iterdir():
            if not item.is_dir():
                continue

            folder_name = item.name
            if not folder_name.endswith("_app"):
                continue

            runner_path = item / "runner.py"
            if not runner_path.exists():
                continue

            app_info = self._parse_app_info(item)
            if not app_info:
                continue

            disk_folders.add(folder_name)

            if folder_name not in registry:
                registry[folder_name] = {
                    "type": "app",
                    "name": app_info["name"],
                    "version": app_info["version"],
                    "description": "Local application",
                    "install_date": current_time,
                    "last_updated": current_time,
                    "branch": "main",
                    "exe_path": "runner.py",
                }
            else:
                stored_ver = registry[folder_name].get("version", "0.0.0")
                if stored_ver != app_info["version"]:
                    registry[folder_name]["version"] = app_info["version"]
                    registry[folder_name]["last_updated"] = current_time

        keys_to_remove = [k for k in registry if k not in disk_folders]
        for k in keys_to_remove:
            del registry[k]

        self._save_installed_apps_cache(registry)
        return registry

    def _parse_app_info(self, app_dir: Path, is_core=False) -> dict:
        const_file = app_dir / "constants.py"
        if not const_file.exists():
            return None
        try:
            content = const_file.read_text(encoding="utf-8")
            name = None
            version = None
            if is_core:
                v_match = re.search(r'CORE_VERSION\s*=\s*["\']([^"\']+)["\']', content)
                if v_match:
                    version = v_match.group(1)
                    name = "Omni Trans Core"
            else:
                n_match = re.search(r'APP_NAME\s*=\s*["\']([^"\']+)["\']', content)
                v_match = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', content)
                if n_match:
                    name = n_match.group(1)
                if v_match:
                    version = v_match.group(1)

            if name and version:
                return {"name": name, "version": version}
        except Exception:
            pass
        return None

    def _load_installed_apps_cache(self):
        if config.INSTALLED_APPS_JSON.exists():
            try:
                with open(config.INSTALLED_APPS_JSON, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_installed_apps_cache(self, data):
        try:
            with open(config.INSTALLED_APPS_JSON, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            console.log(f"[red]Error[/] Failed to save registry: {e}")

    def get_icon(self, app_data: dict) -> QIcon:
        b64 = app_data.get("icon_base64")
        if b64:
            return self._decode_base64_icon(b64)
        folder = app_data.get("folder_name")
        if folder:
            app_path = config.APPS_DIR / folder
            for icon_name in ["icon.png", "logo.png", "app_icon.png", "icon.ico"]:
                icon_file = app_path / icon_name
                if icon_file.exists():
                    return QIcon(str(icon_file))
        return self._decode_base64_icon(DEFAULT_ICON_B64)

    def _decode_base64_icon(self, base64_str):
        try:
            if "," in base64_str:
                base64_str = base64_str.split(",")[1]
            img_data = base64.b64decode(base64_str)
            pixmap = QPixmap()
            pixmap.loadFromData(img_data)
            return QIcon(pixmap)
        except Exception:
            return QIcon()

    def get_core_version(self) -> str:
        registry = self._load_installed_apps_cache()
        core_data = registry.get("omni_trans_core")
        if core_data:
            ver = core_data["version"]
            return ver if ver.startswith("v") else f"v{ver}"
        return "Unknown"

    def get_core_update_info(self):
        registry = self._load_installed_apps_cache()
        core_data = registry.get("omni_trans_core")
        if core_data and core_data.get("pending_update_version"):
            return UpdateInfo(
                component_id="omni_trans_core",
                local_version=core_data["version"],
                remote_version=core_data["pending_update_version"],
                update_type="patch",
                download_url=core_data.get("pending_download_url"),
                changelog=core_data.get("pending_changelog", ""),
                is_critical=core_data.get("is_critical", False),
            )
        return None
    
    def get_launcher_update_info(self):
        registry = self._load_installed_apps_cache()
        data = registry.get("launcher")
        if data and data.get("pending_update_version"):
            return data
        return None

    def get_core_manifest_data(self):
        return self.update_manager.manifest_data.get("core", {})

    def is_installed(self, folder_name: str) -> bool:
        app_path = config.APPS_DIR / folder_name
        return app_path.exists() and (app_path / "runner.py").exists()

    def check_dependencies(self, app_data: dict) -> tuple[bool, str]:
        min_core_req = app_data.get("min_core_version")
        if not min_core_req:
            return True, ""
        registry = self._load_installed_apps_cache()
        core_data = registry.get("omni_trans_core")
        current_core_ver = core_data.get("version", "0.0.0") if core_data else "0.0.0"
        if parse_version(current_core_ver) < parse_version(min_core_req):
            req_str = min_core_req.lstrip("v")
            curr_str = current_core_ver.lstrip("v")
            return (False, f"Required Core: v{req_str}\nInstalled Core: v{curr_str}")
        return True, ""

    def validate_launch(self, folder_name: str) -> tuple[bool, str]:
        registry = self._load_installed_apps_cache()
        app_entry = registry.get(folder_name)
        if not app_entry:
            return False, "App not registered"
        min_core_req = app_entry.get("min_core_version", "0.0.0")
        core_data = registry.get("omni_trans_core")
        current_core_ver = core_data.get("version", "0.0.0") if core_data else "0.0.0"

        if (
            core_data
            and core_data.get("is_critical")
            and core_data.get("pending_update_version")
        ):
            return (
                False,
                f"Critical Core Update Available (v{core_data['pending_update_version']})!",
            )
        if parse_version(current_core_ver) < parse_version(min_core_req):
            return False, f"Core version mismatch! App requires v{min_core_req}"
        return True, ""

    def install_app(self, app_data: dict):
        folder_name = app_data.get("folder_name", app_data.get("id"))
        repo_url = app_data.get("repo_url", "")
        target_version = app_data.get(
            "latest_version", app_data.get("version", "0.0.0")
        )

        filename = app_data.get("archive_name")
        branch = app_data.get("branch", "main")

        description = app_data.get("description", "")
        changelog = app_data.get("changelog", "")

        if not repo_url:
            raise ValueError("Repository URL is missing")

        zip_url = self.update_manager._construct_download_url(
            repo_url, target_version, filename, branch
        )

        console.log(f"Downloading {target_version} from {zip_url}")

        download_path = config.TEMP_DIR / "download_cache"
        download_path.mkdir(exist_ok=True)
        zip_file = download_path / f"{folder_name}.zip"

        response = requests.get(zip_url, stream=True)
        response.raise_for_status()

        with open(zip_file, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        extract_root = config.TEMP_DIR / "extract_cache"
        if extract_root.exists():
            shutil.rmtree(extract_root)
        extract_root.mkdir()

        with zipfile.ZipFile(zip_file, "r") as zf:
            zf.extractall(extract_root)

        source_path = extract_root
        items = list(extract_root.iterdir())
        if len(items) == 1 and items[0].is_dir():
            source_path = items[0]

        target_folder = config.APPS_DIR / folder_name
        if target_folder.exists():
            shutil.rmtree(target_folder)

        shutil.move(str(source_path), str(target_folder))

        parsed_info = self._parse_app_info(
            target_folder, is_core=(folder_name == "omni_trans_core")
        )
        final_version = parsed_info["version"] if parsed_info else target_version
        final_name = (
            parsed_info["name"] if parsed_info else app_data.get("name", folder_name)
        )

        registry = self._load_installed_apps_cache()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        install_date = current_time
        if folder_name in registry:
            install_date = registry[folder_name].get("install_date", current_time)

        registry[folder_name] = {
            "type": "core" if folder_name == "omni_trans_core" else "app",
            "name": final_name,
            "description": description,
            "changelog": changelog,
            "version": final_version,
            "install_date": install_date,
            "last_updated": current_time,
            "branch": branch,
            "exe_path": "runner.py" if folder_name != "omni_trans_core" else None,
            "pending_update_version": None,
            "pending_changelog": None,
            "is_critical": False,
        }
        self._save_installed_apps_cache(registry)

        if zip_file.exists():
            os.remove(zip_file)
        if extract_root.exists():
            shutil.rmtree(extract_root)

    def save_donate_link_preference(self, link: str):
        registry = self._load_installed_apps_cache()
        
        if "launcher" not in registry:
            registry["launcher"] = {
                "type": "launcher",
                "version": config.LAUNCHER_VERSION,
                "name": "Omni Trans Launcher"
            }
            
        registry["launcher"]["donate_link"] = link
        
        self._save_installed_apps_cache(registry)

    def register_launch_and_check_nag(self, app_id: str, is_launcher: bool = False) -> tuple[bool, int]:
        registry = self._load_installed_apps_cache()

        if app_id not in registry:
            if is_launcher:
                registry[app_id] = {
                    "type": "launcher",
                    "version": config.LAUNCHER_VERSION,
                    "name": "Omni Trans Launcher",
                }
            else:
                return False, 0

        current_count = registry[app_id].get("launch_count", 0)
        new_count = current_count + 1
        registry[app_id]["launch_count"] = new_count

        self._save_installed_apps_cache(registry)

        cfg = config.NAG_CONFIG["launcher"] if is_launcher else config.NAG_CONFIG["app"]

        show_nag = False

        if new_count in cfg["milestones"]:
            show_nag = True
        elif new_count > cfg["loop_start"]:
            if (new_count - cfg["loop_start"]) % cfg["loop_step"] == 0:
                show_nag = True

        return show_nag, new_count

    def update_launcher(self, app_data: dict):
        repo_url = app_data.get("repo_url", "")
        version = app_data.get("latest_version", app_data.get("version", "0.0.0"))
        filename = app_data.get("archive_name")
        branch = app_data.get("branch", "main")

        zip_url = self.update_manager._construct_download_url(
            repo_url, version, filename, branch
        )

        update_extract_dir = config.TEMP_DIR / "launcher_update_pkg"
        if update_extract_dir.exists():
            shutil.rmtree(update_extract_dir)
        update_extract_dir.mkdir()

        response = requests.get(zip_url, stream=True)
        response.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            zf.extractall(update_extract_dir)

        source_dir = update_extract_dir
        items = list(update_extract_dir.iterdir())
        if len(items) == 1 and items[0].is_dir():
            source_dir = items[0]

        meta_dir = source_dir / "launcher"
        meta_dir.mkdir(exist_ok=True, parents=True)
        with open(meta_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump({"version": version, "channel": "stable"}, f)

        if not config.UPDATER_TEMPLATE.exists():
            raise FileNotFoundError("Updater template missing")

        template = config.UPDATER_TEMPLATE.read_text(encoding="utf-8")
        run_cmd = "run.bat"
        script_content = (
            template.replace("{{PID}}", str(os.getpid()))
            .replace("{{SOURCE}}", str(source_dir))
            .replace("{{DEST}}", str(config.APPS_DIR))
            .replace("{{LAUNCH_CMD}}", run_cmd)
        )
        run_bat_path = config.TEMP_DIR / "exec_update.bat"
        run_bat_path.write_text(script_content, encoding="utf-8")
        subprocess.Popen([str(run_bat_path)], shell=True, cwd=str(config.APPS_DIR))
        sys.exit(0)

    def run_app_checks(self, folder_name: str):
        console.log(f"[Env: Checking environment for {folder_name}...")
        req_path = config.APPS_DIR / folder_name / "requirements.txt"
        if req_path.exists():
            console.log(f"[Env: Installing dependencies from {req_path}")
            self.uv_manager.install_requirements([req_path])
        else:
            console.log("No requirements.txt found, skipping.")
        return folder_name
