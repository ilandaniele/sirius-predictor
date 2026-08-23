@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\simulate-and-publish.ps1" %*
if errorlevel 1 (
  echo.
  echo No se pudo completar la simulacion local. Revisa el mensaje anterior.
  pause
  exit /b 1
)
echo.
echo Simulacion local publicada correctamente.
pause
