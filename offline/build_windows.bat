@echo off
REM ============================================================
REM Launchkey Mixer — Offline Windows build script
REM Produces a single-file .exe at offline\dist\LaunchkeyMixer.exe
REM
REM Auto-detects yarn / npm and falls back as needed.
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

REM --- Detect package manager (prefer yarn; auto-install yarn via npm if missing) ---
set PKG=
where yarn >nul 2>&1
if %errorlevel%==0 (
    set PKG=yarn
) else (
    where npm >nul 2>&1
    if !errorlevel!==0 (
        echo Yarn not found — installing it globally via npm...
        call npm install -g yarn
        if !errorlevel! NEQ 0 (
            echo *** Failed to install yarn. Falling back to npm directly. ***
            set PKG=npm
        ) else (
            set PKG=yarn
        )
    )
)

if "%PKG%"=="yarn" (
    set PKG_INSTALL=yarn install
    set PKG_BUILD=yarn build
) else if "%PKG%"=="npm" (
    set PKG_INSTALL=npm install --legacy-peer-deps
    set PKG_BUILD=npm run build
)

if "%PKG%"=="" (
    echo.
    echo *** Neither yarn nor npm found on PATH. ***
    echo Install Node.js from https://nodejs.org and re-run.
    exit /b 1
)

echo Using package manager: %PKG%

REM --- Detect python (python.exe vs py launcher) ---
set PY=
where python >nul 2>&1
if %errorlevel%==0 (
    set PY=python
) else (
    where py >nul 2>&1
    if !errorlevel!==0 set PY=py -3
)

if "%PY%"=="" (
    echo.
    echo *** Python not found on PATH. ***
    echo Install Python 3.10-3.12 from https://www.python.org/downloads/
    echo During install, tick "Add Python to PATH".
    exit /b 1
)

echo Using Python: %PY%

echo.
echo === [1/5] Building React frontend ===
pushd ..\frontend
if not exist .env.offline (
    > .env.offline echo REACT_APP_BACKEND_URL=
)
if exist .env copy /Y .env .env.cloud.bak >nul
copy /Y .env.offline .env >nul

REM Try the chosen package manager first; on install failure, fall back to npm.
call %PKG_INSTALL%
if errorlevel 1 (
    if "%PKG%"=="yarn" (
        echo.
        echo *** Yarn install failed - falling back to npm ***
        echo.
        REM Remove yarn.lock so npm doesn't trip on it, then use npm install
        if exist yarn.lock del /Q yarn.lock
        call npm install --legacy-peer-deps
        if errorlevel 1 goto :fail
        set PKG=npm
        set PKG_BUILD=npm run build
    ) else (
        goto :fail
    )
)
call %PKG_BUILD%
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
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo --- Trying optional python-rtmidi (binary-only, faster MIDI) ---
%PY% -m pip install --only-binary=:all: python-rtmidi
if errorlevel 1 (
    echo *** python-rtmidi binary wheel not available for your Python version.
    echo *** No problem - the helper will use the built-in winmm.dll backend.
    set ERRORLEVEL=0
)

echo.
echo === [5/5] Packaging single-file exe with PyInstaller ===
%PY% -m PyInstaller --noconfirm --clean LaunchkeyMixer.spec
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
