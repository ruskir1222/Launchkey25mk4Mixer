@echo off
REM Launchkey Mixer — Windows installer
REM Double-click this file (Python 3.10+ must be on PATH).

setlocal enabledelayedexpansion
echo === Upgrading pip / setuptools / wheel ===
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto fail

echo.
echo === Installing pure-Python deps ===
python -m pip install mido pycaw comtypes requests pynput
if errorlevel 1 goto fail

echo.
echo === Trying python-rtmidi (prebuilt wheel only) ===
python -m pip install --only-binary=:all: python-rtmidi
if errorlevel 1 (
    echo.
    echo [!] No prebuilt python-rtmidi wheel for your Python. Trying 1.5.8 ...
    python -m pip install --only-binary=:all: "python-rtmidi==1.5.8"
)

REM Verify python-rtmidi actually imports
python -c "import rtmidi" 2>nul
if errorlevel 1 (
    echo.
    echo [!] python-rtmidi unavailable. Installing pygame as fallback MIDI backend ...
    python -m pip install pygame
    if errorlevel 1 (
        echo.
        echo [FAIL] Could not install python-rtmidi OR pygame.
        echo Try:  install Python 3.11 or 3.12 and re-run this installer.
        goto fail
    )
    echo [OK] Using pygame MIDI backend.
) else (
    echo [OK] Using python-rtmidi MIDI backend.
)

echo.
echo ===================================================================
echo  All deps installed. Now run:
echo     python launchkey_helper.py --api YOUR_DASHBOARD_URL
echo ===================================================================
echo.
pause
exit /b 0

:fail
echo.
echo Installation failed. See messages above.
pause
exit /b 1
