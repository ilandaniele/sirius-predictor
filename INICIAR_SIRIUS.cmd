@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\start-sirius.ps1" %*
if errorlevel 1 (
  echo.
  echo No se pudo iniciar Sirius. Revisa el mensaje anterior.
  pause
)
