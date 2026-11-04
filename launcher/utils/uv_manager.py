import os
import sys
import shutil
import zipfile
import subprocess
import urllib.request
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

        try:
            urllib.request.urlretrieve(config.UV_DOWNLOAD_URL, zip_path)

            extract_dir = config.TEMP_DIR / "uv_extract"
            if extract_dir.exists():
                shutil.rmtree(extract_dir)

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            found = False
            for item in extract_dir.rglob("uv.exe"):
                if not config.UV_DIR.exists():
                    config.UV_DIR.mkdir(parents=True)

                shutil.move(str(item), str(self.uv_exec))
                found = True
                break

            if not found:
                raise FileNotFoundError("uv.exe not found in downloaded archive")

        finally:
            if zip_path.exists():
                os.remove(zip_path)
            if extract_dir.exists():
                shutil.rmtree(extract_dir)

    def ensure_venv(self):
        if not self.venv_python.exists():
            print("Creating virtual environment...")
            subprocess.run(
                [sys.executable, "-m", "venv", str(config.VENV_DIR)], check=True
            )

    def install_requirements(self, req_files: list[Path]):
        if not req_files:
            return

        cmd = [str(self.uv_exec), "pip", "install"]

        for rf in req_files:
            cmd.append("-r")
            cmd.append(str(rf))

        cmd.extend(["--python", str(self.venv_python)])

        print("Installing dependencies...")
        subprocess.run(cmd, env=self.env, check=True)

    def install_single_package(self, package_name):
        cmd = [
            str(self.uv_exec),
            "pip",
            "install",
            package_name,
            "--python",
            str(self.venv_python),
        ]
        subprocess.run(cmd, env=self.env, check=True)
