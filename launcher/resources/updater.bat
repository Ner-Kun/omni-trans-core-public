@echo off
set PID={{PID}}
set SOURCE={{SOURCE}}
set DEST={{DEST}}
set LAUNCH_CMD={{LAUNCH_CMD}}

title Updating Launcher...
echo Waiting for Launcher (PID: %PID%) to close...

:LOOP
tasklist /FI "PID eq %PID%" 2>NUL | find /I /N "%PID%" >NUL
if "%ERRORLEVEL%"=="0" (
    timeout /t 1 /nobreak >NUL
    goto LOOP
)

echo Process closed. Starting update...
timeout /t 1 /nobreak >NUL

echo Copying new files...
xcopy /E /I /Y "%SOURCE%\*" "%DEST%\"

echo Cleaning up...
rmdir /S /Q "%SOURCE%"

echo Restarting Launcher...
start "" %LAUNCH_CMD%

del "%~f0"