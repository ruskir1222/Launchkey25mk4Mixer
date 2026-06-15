@echo off
REM ==================================================================
REM Launchkey Mini MK4 25 — SysEx Sniff Helper (v2)
REM ==================================================================
REM USBPcap requires Administrator privileges. If you double-click this
REM file and it closes, right-click -> "Run as administrator".
REM ==================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

set USBPCAP="C:\Program Files\USBPcap\USBPcapCMD.exe"
set CAPTURE_FILE=launchkey_capture.pcap
set DECODED_FILE=decoded.txt

REM --- Sanity: USBPcap installed? -----------------------------------
if not exist %USBPCAP% (
    echo.
    echo USBPcap not found at %USBPCAP%
    echo.
    echo Install it from PowerShell (admin):  winget install -e --id USBPcap.USBPcap
    echo Or download:  https://desowin.org/usbpcap/
    echo.
    echo *** Reboot after install. Then re-run this script. ***
    echo.
    pause
    exit /b 1
)

REM --- Sanity: are we elevated? -------------------------------------
net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo *** This script needs to run as ADMINISTRATOR. ***
    echo Close this window, right-click capture.bat, choose "Run as administrator".
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  LAUNCHKEY MK4 MINI - SysEx Capture
echo ============================================================
echo.
echo Step 1) Listing USB buses and what's connected to each.
echo         Find the bus that lists your Launchkey Mini MK4 25.
echo.
%USBPCAP% --extcap-interfaces 2>&1
echo.
echo (If nothing showed up, USBPcap is not loaded - try a reboot.)
echo.

set /p BUS=Step 2) Enter the bus NUMBER your Launchkey is on (just the digit, e.g. 1): 
if "!BUS!"=="" (
    echo No bus entered. Exiting.
    pause
    exit /b 1
)

if exist %CAPTURE_FILE% del /Q %CAPTURE_FILE%

echo.
echo ============================================================
echo  RECORDING starts when you press a key.
echo  Then:
echo   1. Open Novation Components
echo   2. Set Pad 1 red, Pad 2 green, Pad 3 blue (etc., one color each)
echo   3. Click "Send to Launchkey"
echo   4. Change the Custom mode name to HELLO, send again
echo   5. Turn knob 1 from 0 -^> 100 -^> 0 (volume mode)
echo.
echo  When done, COME BACK to this window and press Ctrl+C ONCE to stop.
echo ============================================================
pause

echo Starting capture on \\.\USBPcap!BUS! ...
%USBPCAP% -d \\.\USBPcap!BUS! -o %CAPTURE_FILE%

if not exist %CAPTURE_FILE% (
    echo.
    echo *** No capture file was produced. USBPcap may have errored. ***
    echo Try a different bus number. The number from --extcap-interfaces above
    echo is what you should enter (e.g. if it shows \\.\USBPcap1 enter "1").
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  DECODING capture...
echo ============================================================
set PY=python
where python >nul 2>&1
if errorlevel 1 (
    set PY=py -3
)

%PY% parse_pcap.py %CAPTURE_FILE% --out %DECODED_FILE%
if errorlevel 1 (
    echo.
    echo *** Decode failed. Make sure Wireshark is installed (provides tshark.exe). ***
    echo winget install -e --id WiresharkFoundation.Wireshark
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  DONE.
echo   Raw capture:  %CD%\%CAPTURE_FILE%
echo   Decoded:      %CD%\%DECODED_FILE%
echo.
echo  Paste the contents of %DECODED_FILE% into the chat.
echo ============================================================
pause
