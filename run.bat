@echo off
chcp 65001 > nul
cd /d "%~dp0"


if exist "launcher\start.py" goto :LAUNCH

echo [INFO] Launcher files not found. Starting installation...
echo [INFO] Downloading latest release from GitHub...

curl -L -o omni-trans-launcher.zip "https://github.com/Ner-Kun/omni-trans-core-public/releases/latest/download/omni-trans-launcher.zip"

if %errorlevel% neq 0 (
    echo [ERROR] Failed to download launcher. Please check your internet connection.
    pause
    exit /b
)

echo [INFO] Extracting files...
tar -xf omni-trans-launcher.zip

if %errorlevel% neq 0 (
    echo [ERROR] Failed to extract archive.
    pause
    exit /b
)

del omni-trans-launcher.zip
echo [INFO] Installation complete.


:LAUNCH
where wt.exe >nul 2>nul
if %errorlevel% equ 0 (
    wt.exe --title "Omni Trans Launcher" python launcher\start.py
) else (
    python launcher\start.py
)