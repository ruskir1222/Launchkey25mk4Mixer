@echo off
REM Launchkey Mixer — Windows installer (Python 3.10–3.14)
REM Double-click this file. Python must be on PATH.

setlocal enabledelayedexpansion
echo === Upgrading pip / setuptools / wheel ===
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto fail

echo.
echo === Installing required deps (pycaw, comtypes, requests, pynput) ===
python -m pip install pycaw comtypes requests pynput
if errorlevel 1 (
    echo.
    echo [!] One of pycaw / comtypes / requests / pynput could not install.
    echo     This usually means your Python is too new (3.14+ pre-release^).
    echo     Install Python 3.12 from python.org instead.
    goto fail
)

echo.
echo === Optional: trying python-rtmidi (faster MIDI backend) ===
python -m pip install --only-binary=:all: "python-rtmidi>=1.5.8"
python -c "import rtmidi" 2>nul
if errorlevel 1 (
    echo [.] python-rtmidi not available — that is OK.
    echo === Optional: trying pygame (alternate MIDI backend) ===
    python -m pip install pygame
    python -c "import pygame.midi" 2>nul
    if errorlevel 1 (
        echo [.] pygame not available either — that is OK too.
        echo     Helper will use built-in pure-ctypes WINMM MIDI backend.
    ) else (
        echo [OK] pygame installed.
    )
) else (
    echo [OK] python-rtmidi installed.
)

echo.
echo ===================================================================
echo  Done. Run:
echo     python launchkey_helper.py --api YOUR_DASHBOARD_URL
echo  Or to list MIDI ports first:
echo     python launchkey_helper.py --list-ports
echo ===================================================================
echo.
pause
exit /b 0

:fail
echo.
echo Installation failed. See messages above.
pause
exit /b 1
