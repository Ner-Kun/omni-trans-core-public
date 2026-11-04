import sys
from pathlib import Path

current_script_dir = Path(__file__).resolve().parent
project_root = current_script_dir.parent

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import os  # noqa: E402
import subprocess  # noqa: E402
import urllib.request  # noqa: E402

from launcher import config  # noqa: E402
from launcher.utils.uv_manager import UvManager  # noqa: E402

FALLBACK_REQUIREMENTS = """\
PySide6==6.12.0
PySide6-Fluent-Widgets[full]==1.11.3
requests==2.34.2
rich==15.0.0
packaging==26.3
"""


def fetch_text(url: str) -> str:
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Omni-Trans-Launcher"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.read().decode("utf-8")
    except Exception:
        return ""


def read_local(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def requirements_content() -> str:
    if config.LOCAL_LAUNCHER_REQUIREMENTS.exists():
        return read_local(config.LOCAL_LAUNCHER_REQUIREMENTS)
    if config.LOCAL_CORE_REQUIREMENTS.exists():
        return read_local(config.LOCAL_CORE_REQUIREMENTS)

    remote = fetch_text(config.URL_LAUNCHER_REQ) + "\n" + fetch_text(
        config.URL_CORE_REQ
    )
    return remote.strip() or FALLBACK_REQUIREMENTS


def main():
    uv_man = UvManager()

    try:
        uv_man.ensure_uv()
    except Exception as error:
        print(f"uv is unavailable ({error}); falling back to pip.")

    uv_man.ensure_venv()

    combined_req_path = config.TEMP_DIR / "startup_requirements.txt"
    combined_req_path.write_text(requirements_content(), encoding="utf-8")

    try:
        uv_man.install_requirements([combined_req_path])
    except subprocess.CalledProcessError:
        print("Failed to install dependencies.")
        input("Press Enter to exit...")
        sys.exit(1)

    env = os.environ.copy()
    current_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(config.ROOT_DIR) + os.pathsep + current_pp
    env["FORCE_COLOR"] = "1"

    cmd = [str(config.VENV_PYTHON), "-m", "launcher.entry_point"]

    subprocess.Popen(cmd, cwd=config.ROOT_DIR, env=env).wait()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
