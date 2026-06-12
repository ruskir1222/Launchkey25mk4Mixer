@echo off
REM ============================================================
REM Launchkey Mixer — Offline Windows build script
REM Produces a single-file .exe at offline\dist\LaunchkeyMixer.exe
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo === [1/5] Building React frontend ===
pushd ..\frontend
if not exist .env.offline (
    echo REACT_APP_BACKEND_URL=> .env.offline
)
copy /Y .env .env.cloud.bak >nul 2>&1
copy /Y .env.offline .env >nul
call yarn install
if errorlevel 1 goto :fail
call yarn build
if errorlevel 1 goto :fail
if exist .env.cloud.bak (
    copy /Y .env.cloud.bak .env >nul
    del .env.cloud.bak >nul
)
popd

echo.
echo === [2/5] Copying frontend build into offline\static ===
if exist static rmdir /S /Q static
mkdir static
xcopy /E /I /Y ..\frontend\build\* static\ >nul
if errorlevel 1 goto :fail

echo.
echo === [3/5] Copying helper script into offline\helper ===
if exist helper rmdir /S /Q helper
mkdir helper
xcopy /E /I /Y ..\backend\helper\* helper\ >nul
if errorlevel 1 goto :fail

echo.
echo === [4/5] Installing Python build dependencies ===
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo === [5/5] Packaging single-file exe with PyInstaller ===
python -m PyInstaller --noconfirm --clean LaunchkeyMixer.spec
if errorlevel 1 goto :fail

echo.
echo ===============================================================
echo  SUCCESS — your offline app is at:
echo    %CD%\dist\LaunchkeyMixer.exe
echo ===============================================================
echo  Double-click LaunchkeyMixer.exe to launch.
echo  The dashboard opens automatically in your browser.
echo ===============================================================
goto :eof

:fail
echo.
echo *** Build failed ***
exit /b 1
