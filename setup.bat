@echo off
REM CopyLane bootstrap entry point.
REM Keep this file ASCII-only: cmd.exe uses the OEM code page.
REM .bat is not subject to the PowerShell execution policy, .ps1 is.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
pause
