@echo off
REM ==================================================================
REM Launchkey Mini MK4 25 — SysEx Sniff Helper
REM
REM Walks through the steps needed to record Novation Components
REM traffic and produce a decoded.txt for sharing.
REM ==================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

set USBPCAP="C:\Program Files\USBPcap\USBPcapCMD.exe"

echo.
echo === Launchkey MK4 Mini SysEx Capture ===
echo.

if not exist %USBPCAP% (
    echo USBPcap not found. Installing via winget...
    winget install -e --id USBPcap.USBPcap
    echo.
    echo *** REBOOT YOUR PC, then re-run this script. ***
    pause
    exit /b 1
)

echo Listing USB buses. Look for one connected to your Launchkey.
echo.
%USBPCAP% --extcap-interfaces 2>nul
%USBPCAP% -d \\.\USBPcap1 -o NUL --start 2>nul
echo.
set /p BUS=Enter the USBPcap bus number where your Launchkey is (e.g. 1, 2, 3): 

set CAPTURE_FILE=launchkey_capture.pcap
if exist %CAPTURE_FILE% del /Q %CAPTURE_FILE%

echo.
echo === RECORDING — press Ctrl+C when done ===
echo Open Novation Components NOW and perform the steps in README.md (section 4).
echo.

%USBPCAP% -d \\.\USBPcap%BUS% -o %CAPTURE_FILE%

echo.
echo === DECODING ===
where python >nul 2>&1 && (
    python parse_pcap.py %CAPTURE_FILE% --out decoded.txt
) || (
    py -3 parse_pcap.py %CAPTURE_FILE% --out decoded.txt
)
if errorlevel 1 (
    echo *** decode failed - check that Wireshark is installed (provides tshark.exe) ***
    pause
    exit /b 1
)

echo.
echo === DONE ===
echo  Capture:  %CD%\%CAPTURE_FILE%
echo  Decoded:  %CD%\decoded.txt
echo.
echo Share decoded.txt with the next agent / chat session.
pause
