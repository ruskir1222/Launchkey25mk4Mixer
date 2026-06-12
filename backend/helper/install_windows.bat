@echo off
REM Launchkey Mixer — one-click Windows installer
REM Usage: double-click install_windows.bat (must have Python 3.10+ on PATH)

setlocal
echo === Upgrading pip / setuptools / wheel (needed for prebuilt wheels) ===
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto fail

echo.
echo === Installing pure-Python deps first ===
python -m pip install mido pycaw comtypes requests pynput
if errorlevel 1 goto fail

echo.
echo === Installing python-rtmidi (prebuilt wheel only — avoids C++ build) ===
python -m pip install --only-binary=:all: python-rtmidi
if errorlevel 1 (
    echo.
    echo [!] No prebuilt wheel matched your Python version.
    echo     Trying the most recent known-good version 1.5.8 ...
    python -m pip install --only-binary=:all: "python-rtmidi==1.5.8"
)
if errorlevel 1 (
    echo.
    echo [!] python-rtmidi still failed. Options:
    echo     1^) Install Python 3.11 or 3.12 (widest wheel coverage^)
    echo     2^) Install "Microsoft C++ Build Tools" (Desktop dev with C++) then re-run.
    echo     3^) Try:   pip install rtmidi2   (then edit helper to use rtmidi2^)
    goto fail
)

echo.
echo === All deps installed. Now run: ===
echo     python launchkey_helper.py --api YOUR_DASHBOARD_URL
echo.
pause
exit /b 0

:fail
echo.
echo Installation failed. See messages above.
pause
exit /b 1
