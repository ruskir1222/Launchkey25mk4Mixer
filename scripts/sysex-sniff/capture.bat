@echo off
REM ==================================================================
REM Launchkey Mini MK4 25 — SysEx Sniff Helper (v3)
REM
REM Bulletproof version: every code path ends at the :end label which
REM ALWAYS pauses, so the cmd window never disappears before you can
REM read what happened.
REM ==================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "STATUS=unknown"
set "CAPTURE_FILE=launchkey_capture.pcap"
set "DECODED_FILE=decoded.txt"

echo.
echo ============================================================
echo  LAUNCHKEY MK4 MINI - SysEx Capture (script started)
echo ============================================================
echo.
echo Working dir: %CD%
echo.

REM --- Locate USBPcap in either Program Files variant -------------
set "USBPCAP="
if exist "C:\Program Files\USBPcap\USBPcapCMD.exe"       set "USBPCAP=C:\Program Files\USBPcap\USBPcapCMD.exe"
if exist "C:\Program Files (x86)\USBPcap\USBPcapCMD.exe" set "USBPCAP=C:\Program Files (x86)\USBPcap\USBPcapCMD.exe"

if "!USBPCAP!"=="" (
    echo USBPcap not found in:
    echo   C:\Program Files\USBPcap\USBPcapCMD.exe
    echo   C:\Program Files ^(x86^)\USBPcap\USBPcapCMD.exe
    echo.
    echo Install it first:
    echo   1^) Open PowerShell as administrator
    echo   2^) winget install -e --id USBPcap.USBPcap
    echo   3^) REBOOT, then re-run this script.
    echo.
    set "STATUS=usbpcap_missing"
    goto :end
)
echo Found USBPcap at: !USBPCAP!
echo.

REM --- Check admin elevation --------------------------------------
net session >nul 2>&1
if errorlevel 1 (
    echo *** Not running as Administrator. ***
    echo USBPcap needs admin to capture USB traffic.
    echo.
    echo Close this window, right-click capture.bat, choose
    echo "Run as administrator", and try again.
    echo.
    set "STATUS=not_admin"
    goto :end
)
echo Running with admin privileges. OK.
echo.

REM --- Check tshark (decoder needs it) ----------------------------
set "TSHARK="
if exist "C:\Program Files\Wireshark\tshark.exe"       set "TSHARK=C:\Program Files\Wireshark\tshark.exe"
if exist "C:\Program Files (x86)\Wireshark\tshark.exe" set "TSHARK=C:\Program Files (x86)\Wireshark\tshark.exe"

if "!TSHARK!"=="" (
    echo WARNING: tshark not found. The capture step will work, but the
    echo decode step will fail. Install Wireshark to get tshark:
    echo   winget install -e --id WiresharkFoundation.Wireshark
    echo Continuing anyway - you can decode the .pcap later.
    echo.
) else (
    echo Found tshark at: !TSHARK!
    set "PATH=!PATH!;C:\Program Files\Wireshark;C:\Program Files (x86)\Wireshark"
    echo.
)

REM --- List buses ------------------------------------------------
echo ============================================================
echo  Step 1) Listing USB buses. Find the one that includes your
echo          Launchkey Mini MK4 25 in the device tree below.
echo ============================================================
echo.
"!USBPCAP!" --extcap-interfaces 2>&1
echo.
echo (If nothing was listed above, USBPcap driver is not loaded -
echo  try a reboot.)
echo.

set "BUS="
set /p BUS=Step 2) Enter the bus number (e.g. 1, 2, 3): 

if "!BUS!"=="" (
    echo No bus entered. Exiting.
    set "STATUS=no_bus_entered"
    goto :end
)

if exist "%CAPTURE_FILE%" del /Q "%CAPTURE_FILE%"

echo.
echo ============================================================
echo  Step 3) RECORDING is about to start on \\.\USBPcap!BUS!
echo.
echo  Press any key here, then immediately:
echo    1. Open Novation Components
echo    2. Set Pad 1 RED, Pad 2 GREEN, Pad 3 BLUE etc. (any 4-8 colors)
echo    3. Click "Send to Launchkey"
echo    4. Change Custom mode name to "HELLO", send again
echo    5. Switch to volume mode, turn knob 1 from 0 to 100 and back
echo.
echo  WHEN DONE: come back to this window and press Ctrl+C to stop.
echo ============================================================
pause

echo Capturing to %CAPTURE_FILE% ...
"!USBPCAP!" -d \\.\USBPcap!BUS! -o "%CAPTURE_FILE%"

if not exist "%CAPTURE_FILE%" (
    echo.
    echo *** No capture file produced. The bus number may have been wrong,
    echo *** or no USB traffic occurred on that bus during the capture.
    echo *** Try running again and pick a different bus number.
    set "STATUS=no_capture"
    goto :end
)
echo.
echo Capture saved: %CAPTURE_FILE%
echo.

echo ============================================================
echo  Step 4) Decoding capture into %DECODED_FILE% ...
echo ============================================================
set "PY=python"
where python >nul 2>&1
if errorlevel 1 (
    where py >nul 2>&1
    if errorlevel 1 (
        echo Python not found - install from python.org and re-run parse_pcap.py manually.
        set "STATUS=no_python"
        goto :end
    )
    set "PY=py -3"
)

%PY% parse_pcap.py "%CAPTURE_FILE%" --out "%DECODED_FILE%"
if errorlevel 1 (
    echo *** Decode failed. Common cause: tshark not on PATH.
    echo *** Install Wireshark: winget install -e --id WiresharkFoundation.Wireshark
    set "STATUS=decode_failed"
    goto :end
)

set "STATUS=success"

:end
echo.
echo ============================================================
if "!STATUS!"=="success" (
    echo  DONE - STATUS: success
    echo   Raw capture:   %CD%\%CAPTURE_FILE%
    echo   Decoded text:  %CD%\%DECODED_FILE%
    echo.
    echo  Open %DECODED_FILE% in Notepad and paste contents into chat.
) else (
    echo  EXIT STATUS: !STATUS!
    echo  See messages above for what went wrong.
)
echo ============================================================
echo.
echo Press any key to close this window...
pause >nul
exit /b 0
