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


def fetch_text(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Omni-Trans-Launcher"})
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.read().decode("utf-8")
    except Exception:
        return ""


def main():
    uv_man = UvManager()

    uv_man.ensure_uv()
    uv_man.ensure_venv()

    req_launcher = fetch_text(config.URL_LAUNCHER_REQ)
    req_core = fetch_text(config.URL_CORE_REQ)

    combined_req_path = config.TEMP_DIR / "startup_requirements.txt"

    content = req_launcher + "\n" + req_core
    if "rich" not in content:
        content += "\nrich"

    with open(combined_req_path, "w", encoding="utf-8") as f:
        f.write(content)

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
