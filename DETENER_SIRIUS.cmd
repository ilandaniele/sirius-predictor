@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\stop-sirius.ps1"
if errorlevel 1 pause
