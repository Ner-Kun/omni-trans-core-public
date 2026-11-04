import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

import psutil
import requests
from PySide6.QtGui import QIcon, QPixmap
from packaging.version import parse as parse_version
from rich.console import Console

from launcher import config
from launcher.utils.update_manager import UpdateInfo, UpdateManager
from launcher.utils.uv_manager import UvManager

console = Console()
DEFAULT_ICON_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="


def _download_archive(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=(10, 120)) as response:
        response.raise_for_status()
        with open(destination, "wb") as f:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)


def _safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "r") as zf:
        for member in zf.infolist():
            path = PurePosixPath(member.filename)
            if not path.parts:
                continue
            if path.is_absolute() or ".." in path.parts or ":" in path.parts[0]:
                raise ValueError(f"Unsafe archive member: {member.filename}")
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"Archive contains a symlink: {member.filename}")

            target = destination.joinpath(*path.parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


def _rename_with_retry(source: Path, destination: Path, attempts: int = 5) -> None:
    for attempt in range(attempts):
        try:
            source.rename(destination)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.25)


def _swap_folder(source: Path, target: Path) -> None:
    backup = target.with_name(f"{target.name}.backup")
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)
    if target.exists():
        _rename_with_retry(target, backup)

    try:
        shutil.move(str(source), str(target))
    except Exception:
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        if backup.exists():
            _rename_with_retry(backup, target)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)


def _required_entry(folder_name: str) -> str:
    return "constants.py" if folder_name == "omni_trans_core" else "runner.py"


def _find_source_root(extract_dir: Path, folder_name: str) -> Path:
    required = _required_entry(folder_name)
    candidates = [extract_dir]
    candidates.extend(sorted(p for p in extract_dir.iterdir() if p.is_dir()))

    for candidate in candidates:
        if (candidate / required).exists():
            return candidate

    for candidate in candidates:
        for child in sorted(candidate.iterdir()):
            if child.is_dir() and (child / required).exists():
                return child

    raise ValueError(f"Archive does not contain {required}")


def _find_launcher_root(extract_dir: Path) -> Path:
    candidates = [extract_dir]
    candidates.extend(sorted(p for p in extract_dir.iterdir() if p.is_dir()))

    def is_launcher_root(path: Path) -> bool:
        return (path / "launcher" / "start.py").exists() or (path / "run.bat").exists()

    for candidate in candidates:
        if is_launcher_root(candidate):
            return candidate

    for candidate in candidates:
        for child in sorted(candidate.iterdir()):
            if child.is_dir() and is_launcher_root(child):
                return child

    raise ValueError("Launcher archive does not contain launcher/start.py or run.bat")


class AppManager:
    def __init__(self):
        console.log("AppManager initialized.")
        self.update_manager = UpdateManager(config.APPS_DIR, config.MANIFEST_URL)
        self.uv_manager = UvManager()

    def get_catalog(self, check_updates: bool = True):
        console.log("Catalog synchronization...")

        self.scan_local_apps()
        local_registry = self._load_installed_apps_cache()

        is_online = self.update_manager.fetch_manifest()
        remote_data = self.update_manager.manifest_data

        registry_dirty = False

        if is_online:
            console.log("Processing metadata...")
            remote_apps = remote_data.get("apps", [])
            remote_map = {
                app.get("folder_name", app.get("id")): app for app in remote_apps
            }

            if "core" in remote_data:
                core_entry = dict(remote_data["core"])
                core_entry["id"] = "core"
                remote_map["omni_trans_core"] = core_entry

            if "launcher" in remote_data:
                remote_map["launcher"] = dict(remote_data["launcher"])

            for folder, local_data in local_registry.items():
                if folder not in remote_map:
                    continue

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
                        f"[Criticality] Updated barrier for {folder}: "
                        f"{last_known_critical} -> {remote_ver}"
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
                local_data["archive_name"] = remote_app.get(
                    "archive_name", local_data.get("archive_name")
                )
                local_data["branch"] = remote_app.get(
                    "branch", local_data.get("branch", "main")
                )
                if remote_app.get("icon_base64"):
                    local_data["icon_base64"] = remote_app.get("icon_base64")

                if check_updates and not local_data.get("changelog"):
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

            if check_updates:
                updates_list = self.update_manager.check_updates(local_registry)

                for app_key in local_registry:
                    local_registry[app_key].pop("pending_update_version", None)
                    local_registry[app_key].pop("pending_changelog", None)
                    local_registry[app_key]["is_critical"] = False

                for update in updates_list:
                    comp_id = update.component_id
                    if comp_id not in local_registry:
                        continue

                    console.log(f"Caching new update info for {comp_id}")
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
                            f"{comp_id} marked CRITICAL "
                            f"(Local {local_ver} < Barrier {barrier_ver})"
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
                item["is_running"] = self.is_app_running(folder)

                if local_data and local_data.get("icon_base64"):
                    if not item.get("icon_base64"):
                        item["icon_base64"] = local_data["icon_base64"]

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
            item["is_running"] = self.is_app_running(folder)
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
                "name": config.APP_NAME,
                "version": config.LAUNCHER_VERSION,
                "install_date": current_time,
                "last_updated": current_time,
                "branch": "main",
            }
        elif registry[launcher_key].get("version") != config.LAUNCHER_VERSION:
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

    def _parse_app_info(self, app_dir: Path, is_core=False) -> dict | None:
        const_file = app_dir / "constants.py"
        if not const_file.exists():
            return None
        try:
            content = const_file.read_text(encoding="utf-8")
            name = None
            version = None
            if is_core:
                v_match = re.search(
                    r'CORE_VERSION\s*=\s*["\']([^"\']+)["\']', content
                )
                if v_match:
                    version = v_match.group(1)
                    name = "Omni Trans Core"
            else:
                n_match = re.search(r'APP_NAME\s*=\s*["\']([^"\']+)["\']', content)
                v_match = re.search(
                    r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', content
                )
                if n_match:
                    name = n_match.group(1)
                if v_match:
                    version = v_match.group(1)

            if name and version:
                return {"name": name, "version": version}
        except OSError:
            pass
        return None

    def _load_installed_apps_cache(self) -> dict:
        if config.INSTALLED_APPS_JSON.exists():
            try:
                with open(config.INSTALLED_APPS_JSON, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data if isinstance(data, dict) else {}
            except (OSError, json.JSONDecodeError):
                return {}
        return {}

    def _save_installed_apps_cache(self, data: dict) -> None:
        try:
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            temp_path = config.INSTALLED_APPS_JSON.with_suffix(".tmp")
            temp_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            temp_path.replace(config.INSTALLED_APPS_JSON)
        except OSError as error:
            console.log(f"[red]Error[/] Failed to save registry: {error}")

    def get_app_entry(self, folder_name: str) -> dict:
        return self._load_installed_apps_cache().get(folder_name, {})

    def get_exe_path(self, folder_name: str) -> str:
        return self.get_app_entry(folder_name).get("exe_path") or "runner.py"

    def is_app_running(self, folder_name: str) -> bool:
        exe_path = self.get_exe_path(folder_name)
        if not exe_path:
            return False

        target = str(config.APPS_DIR / folder_name / exe_path).lower().replace(
            "/", "\\"
        )
        module = f"-m {folder_name}.runner".lower()

        try:
            for proc in psutil.process_iter(["pid", "cmdline"]):
                if proc.pid == os.getpid():
                    continue
                try:
                    cmdline = " ".join(
                        (proc.info or {}).get("cmdline") or []
                    ).lower().replace("/", "\\")
                except (psutil.Error, OSError):
                    continue
                if target in cmdline or module in cmdline:
                    return True
        except (psutil.Error, OSError):
            return False

        return False

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

    def _decode_base64_icon(self, base64_str: str) -> QIcon:
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

    def get_core_update_info(self) -> UpdateInfo | None:
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

    def get_launcher_update_info(self) -> dict | None:
        registry = self._load_installed_apps_cache()
        data = registry.get("launcher")
        if data and data.get("pending_update_version"):
            info = dict(data)
            info["latest_version"] = data["pending_update_version"]
            info["changelog"] = data.get("pending_changelog", "")
            return info
        return None

    def get_core_manifest_data(self) -> dict:
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
            return (
                False,
                f"Required Core: v{req_str}\nInstalled Core: v{curr_str}",
            )
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
                f"Critical Core Update Available "
                f"(v{core_data['pending_update_version']})!",
            )
        if parse_version(current_core_ver) < parse_version(min_core_req):
            return False, f"Core version mismatch! App requires v{min_core_req}"
        return True, ""

    def install_app(self, app_data: dict) -> dict:
        folder_name = app_data.get("folder_name", app_data.get("id"))
        if not folder_name:
            raise ValueError("Application folder name is missing")

        repo_url = app_data.get("repo_url", "")
        if not repo_url:
            raise ValueError("Repository URL is missing")

        target_version = app_data.get(
            "latest_version", app_data.get("version", "0.0.0")
        )
        filename = app_data.get("archive_name")
        branch = app_data.get("branch", "main")
        description = app_data.get("description", "")
        changelog = app_data.get("changelog", "")

        zip_url = self.update_manager._construct_download_url(
            repo_url, target_version, filename, branch
        )
        console.log(f"Downloading {target_version} from {zip_url}")

        download_dir = config.TEMP_DIR / "downloads"
        download_dir.mkdir(parents=True, exist_ok=True)
        zip_file = download_dir / f"{folder_name}.zip"
        extract_dir = config.TEMP_DIR / "extract" / folder_name
        if extract_dir.exists():
            shutil.rmtree(extract_dir, ignore_errors=True)
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            _download_archive(zip_url, zip_file)
            _safe_extract(zip_file, extract_dir)
            source_path = _find_source_root(extract_dir, folder_name)
            target_folder = config.APPS_DIR / folder_name
            _swap_folder(source_path, target_folder)
        finally:
            if zip_file.exists():
                zip_file.unlink()
            if extract_dir.exists():
                shutil.rmtree(extract_dir, ignore_errors=True)

        parsed_info = self._parse_app_info(
            target_folder, is_core=(folder_name == "omni_trans_core")
        )
        final_version = parsed_info["version"] if parsed_info else target_version
        final_name = (
            parsed_info["name"] if parsed_info else app_data.get("name", folder_name)
        )

        registry = self._load_installed_apps_cache()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        previous = registry.get(folder_name, {})
        exe_path = (
            previous.get("exe_path")
            or app_data.get("exe_path")
            or "runner.py"
        )
        entry = dict(previous)
        entry.update(
            {
                "type": "core" if folder_name == "omni_trans_core" else "app",
                "name": final_name,
                "description": description,
                "changelog": changelog,
                "version": final_version,
                "install_date": previous.get("install_date", current_time),
                "last_updated": current_time,
                "branch": branch,
                "exe_path": (
                    exe_path if folder_name != "omni_trans_core" else None
                ),
                "pending_update_version": None,
                "pending_changelog": None,
                "is_critical": False,
            }
        )
        registry[folder_name] = entry
        self._save_installed_apps_cache(registry)

        return {
            "folder_name": folder_name,
            "name": final_name,
            "version": final_version,
        }

    def save_donate_link_preference(self, link: str) -> None:
        registry = self._load_installed_apps_cache()

        if "launcher" not in registry:
            registry["launcher"] = {
                "type": "launcher",
                "version": config.LAUNCHER_VERSION,
                "name": config.APP_NAME,
            }

        registry["launcher"]["donate_link"] = link
        self._save_installed_apps_cache(registry)

    def register_launch_and_check_nag(
        self, app_id: str, is_launcher: bool = False
    ) -> tuple[bool, int]:
        registry = self._load_installed_apps_cache()

        if app_id not in registry:
            if is_launcher:
                registry[app_id] = {
                    "type": "launcher",
                    "version": config.LAUNCHER_VERSION,
                    "name": config.APP_NAME,
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

    def update_launcher(self, app_data: dict) -> None:
        repo_url = app_data.get("repo_url", "")
        version = (
            app_data.get("pending_update_version")
            or app_data.get("latest_version")
            or app_data.get("version", "0.0.0")
        )
        filename = app_data.get("archive_name")
        branch = app_data.get("branch", "main")

        zip_url = self.update_manager._construct_download_url(
            repo_url, version, filename, branch
        )

        update_dir = config.TEMP_DIR / "launcher_update"
        if update_dir.exists():
            shutil.rmtree(update_dir, ignore_errors=True)
        update_dir.mkdir(parents=True, exist_ok=True)
        zip_file = update_dir / "launcher.zip"
        extract_dir = update_dir / "extract"

        success = False
        try:
            _download_archive(zip_url, zip_file)
            _safe_extract(zip_file, extract_dir)
            source_dir = _find_launcher_root(extract_dir)

            meta_dir = source_dir / "launcher"
            meta_dir.mkdir(exist_ok=True, parents=True)
            (meta_dir / "metadata.json").write_text(
                json.dumps({"version": version, "channel": "stable"}),
                encoding="utf-8",
            )

            if not config.UPDATER_TEMPLATE.exists():
                raise FileNotFoundError("Updater template missing")

            template = config.UPDATER_TEMPLATE.read_text(encoding="utf-8")
            script_content = (
                template.replace("{{PID}}", str(os.getpid()))
                .replace("{{SOURCE}}", str(source_dir))
                .replace("{{DEST}}", str(config.APPS_DIR))
                .replace("{{LAUNCH_CMD}}", "run.bat")
            )
            run_bat_path = config.TEMP_DIR / "exec_update.bat"
            run_bat_path.write_text(script_content, encoding="utf-8")
            subprocess.Popen(
                ["cmd", "/c", str(run_bat_path)],
                cwd=str(config.APPS_DIR),
            )
            success = True
        finally:
            if zip_file.exists():
                zip_file.unlink()
            if not success and extract_dir.exists():
                shutil.rmtree(extract_dir, ignore_errors=True)

    def run_app_checks(self, folder_name: str) -> str:
        console.log(f"Checking environment for {folder_name}...")
        req_path = config.APPS_DIR / folder_name / "requirements.txt"
        if not req_path.exists():
            console.log("No requirements.txt found, skipping.")
            return folder_name

        digest = hashlib.sha256(req_path.read_bytes()).hexdigest()
        root_req = config.LOCAL_CORE_REQUIREMENTS
        root_stamp = str(root_req.stat().st_mtime_ns) if root_req.exists() else "none"
        venv_stamp = (
            str(config.VENV_PYTHON.stat().st_mtime_ns)
            if config.VENV_PYTHON.exists()
            else "missing"
        )
        marker_value = f"{digest}:{root_stamp}:{venv_stamp}"
        marker = config.TEMP_DIR / f"{folder_name}.requirements.sha256"

        if (
            marker.exists()
            and marker.read_text(encoding="utf-8").strip() == marker_value
            and config.VENV_PYTHON.exists()
        ):
            console.log("Dependencies are up to date.")
            return folder_name

        console.log(f"Installing dependencies from {req_path}")
        self.uv_manager.install_requirements([req_path])
        marker.write_text(marker_value, encoding="utf-8")
        return folder_name
