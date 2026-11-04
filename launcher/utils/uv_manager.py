import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from launcher import config


class UvManager:
    def __init__(self):
        self.uv_exec = config.UV_EXEC
        self.venv_python = config.VENV_PYTHON
        self.env = os.environ.copy()
        self.env["UV_CACHE_DIR"] = str(config.UV_CACHE_DIR)

    def ensure_uv(self):
        if self.uv_exec.exists():
            return

        print("Downloading uv...")
        zip_path = config.TEMP_DIR / "uv.zip"
        extract_dir = config.TEMP_DIR / "uv_extract"

        try:
            request = urllib.request.Request(
                config.UV_DOWNLOAD_URL,
                headers={"User-Agent": "Omni-Trans-Launcher"},
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                with open(zip_path, "wb") as f:
                    shutil.copyfileobj(response, f)

            if extract_dir.exists():
                shutil.rmtree(extract_dir)

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            found = next(extract_dir.rglob("uv.exe"), None)
            if not found:
                raise FileNotFoundError("uv.exe not found in downloaded archive")

            config.UV_DIR.mkdir(parents=True, exist_ok=True)
            shutil.move(str(found), str(self.uv_exec))
        finally:
            if zip_path.exists():
                os.remove(zip_path)
            if extract_dir.exists():
                shutil.rmtree(extract_dir, ignore_errors=True)

    def venv_is_healthy(self) -> bool:
        if not self.venv_python.exists():
            return False
        try:
            result = subprocess.run(
                [str(self.venv_python), "-c", "import sys"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def ensure_venv(self):
        if self.venv_is_healthy():
            return

        if config.VENV_DIR.exists():
            print("Virtual environment is broken; recreating...")
            shutil.rmtree(config.VENV_DIR, ignore_errors=True)

        print("Creating virtual environment...")
        subprocess.run(
            [sys.executable, "-m", "venv", str(config.VENV_DIR)],
            check=True,
        )

    def install_requirements(self, req_files: list[Path]):
        if not req_files:
            return

        if self.uv_exec.exists():
            cmd = [str(self.uv_exec), "pip", "install"]
            for rf in req_files:
                cmd.extend(["-r", str(rf)])
            cmd.extend(["--python", str(self.venv_python)])
        else:
            cmd = [str(self.venv_python), "-m", "pip", "install"]
            for rf in req_files:
                cmd.extend(["-r", str(rf)])

        print("Installing dependencies...")
        subprocess.run(cmd, env=self.env, check=True)

    def install_single_package(self, package_name):
        if self.uv_exec.exists():
            cmd = [
                str(self.uv_exec),
                "pip",
                "install",
                package_name,
                "--python",
                str(self.venv_python),
            ]
        else:
            cmd = [str(self.venv_python), "-m", "pip", "install", package_name]

        subprocess.run(cmd, env=self.env, check=True)
