@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\simulate-and-publish.ps1" -FormatSize 48 %*
if errorlevel 1 (
  echo.
  echo No se pudo completar la simulacion local. Revisa el mensaje anterior.
  pause
  exit /b 1
)
echo.
echo Simulacion local de 48 equipos publicada correctamente.
pause
