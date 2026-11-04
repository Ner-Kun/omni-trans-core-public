import requests
import re
from pathlib import Path
from packaging.version import parse as parse_version
from rich.console import Console

console = Console()


class UpdateInfo:
    def __init__(
        self,
        component_id,
        local_version,
        remote_version,
        update_type,
        download_url,
        changelog,
        is_critical=False,
    ):
        self.component_id = component_id
        self.local_version = local_version
        self.remote_version = remote_version
        self.update_type = update_type
        self.download_url = download_url
        self.changelog = changelog
        self.is_critical = is_critical


class UpdateManager:
    def __init__(self, root_dir, manifest_url):
        self.root_dir = Path(root_dir)
        self.manifest_url = manifest_url
        self.manifest_data = {}
        self.headers = {
            "User-Agent": "Omni-Trans-Launcher",
            "Accept": "application/vnd.github.v3+json",
        }

    def fetch_manifest(self):
        console.log(f"Network: Fetching manifest from: {self.manifest_url}")
        try:
            response = requests.get(self.manifest_url, headers=self.headers, timeout=5)
            response.raise_for_status()
            self.manifest_data = response.json()
            if not isinstance(self.manifest_data, dict):
                console.log("Error: Manifest is not a JSON object.")
                self.manifest_data = {}
                return False
            return True
        except Exception as e:
            console.log(f"[Error: Manifest fetch failed: {e}")
            return False

    def _construct_download_url(self, repo_url, version, filename=None, branch="main"):
        clean_url = repo_url.rstrip("/")
        if clean_url.endswith(".git"):
            clean_url = clean_url[:-4]

        if filename:
            tag = version if version.startswith("v") else f"v{version}"
            return f"{clean_url}/releases/download/{tag}/{filename}"

        return f"{clean_url}/archive/refs/heads/{branch}.zip"

    def fetch_github_release_notes(self, repo_url, version):
        if not repo_url or "github.com" not in repo_url:
            return None

        console.log(f"Fetching notes for {version} from {repo_url}")

        try:
            match = re.search(r"github\.com/([^/]+)/([^/]+)", repo_url)
            if not match:
                console.log("Error: Invalid GitHub URL")
                return None

            owner, repo = match.groups()
            if repo.endswith(".git"):
                repo = repo[:-4]

            api_url = f"https://api.github.com/repos/{owner}/{repo}/releases"
            resp = requests.get(api_url, headers=self.headers, timeout=5)

            if resp.status_code != 200:
                console.log(f"Error: API returned {resp.status_code}")
                return None

            releases = resp.json()
            if not releases:
                console.log("Warning: No releases found in repo.")
                return None

            target_v = version.lstrip("v")

            for rel in releases:
                rel_tag = rel.get("tag_name", "").lstrip("v")
                if rel_tag == target_v:
                    console.log(
                        f"GitHub: Found exact match: {rel.get('tag_name')}"
                    )
                    console.log("Notes fetched.")
                    return rel.get("body", "")

            latest = releases[0]
            tag = latest.get("tag_name", "unknown")
            console.log(
                f"GitHub:Exact match not found. Using newest available: {tag}"
            )
            console.log("[Notes fetched (fallback).")

            return (
                f"**Note:** Showing notes for latest release ({tag}).\n\n"
                + latest.get("body", "")
            )

        except Exception as e:
            console.log(f"[red]Error[/] Exception: {e}")
            pass

        return None

    def check_updates(self, local_registry: dict):
        updates = []
        if not self.manifest_data:
            return []

        core_info = self.manifest_data.get("core")
        if core_info:
            updates.extend(
                self._compare_component("omni_trans_core", core_info, local_registry)
            )

        launcher_info = self.manifest_data.get("launcher")
        if launcher_info:
            updates.extend(
                self._compare_component("launcher", launcher_info, local_registry)
            )

        apps_list = self.manifest_data.get("apps", [])
        for app_entry in apps_list:
            folder = app_entry.get("folder_name", app_entry.get("id"))
            updates.extend(self._compare_component(folder, app_entry, local_registry))

        return updates

    def _compare_component(self, component_id, remote_data, local_registry):
        local_entry = local_registry.get(component_id)
        local_ver = local_entry.get("version", "0.0.0") if local_entry else "0.0.0"
        remote_ver = remote_data.get("version", "0.0.0")

        console.log(
            f"Check {component_id}: Local {local_ver} vs Remote {remote_ver}"
        )

        if parse_version(remote_ver) > parse_version(local_ver):
            console.log(
                f"!!!Update Found {component_id}: {local_ver} -> {remote_ver}!!!"
            )

            changelog = self.fetch_github_release_notes(
                remote_data.get("repo_url"), remote_ver
            )
            if not changelog:
                changelog = remote_data.get("changelog", "")

            download_url = self._construct_download_url(
                remote_data.get("repo_url", ""),
                remote_ver,
                remote_data.get("archive_name"),
                remote_data.get("branch", "main"),
            )

            return [
                UpdateInfo(
                    component_id=component_id,
                    local_version=local_ver,
                    remote_version=remote_ver,
                    update_type=remote_data.get("update_type", "patch"),
                    download_url=download_url,
                    changelog=changelog,
                    is_critical=remote_data.get("critical", False),
                )
            ]
        else:
            console.log(f"{component_id} is up to date.")

        return []
