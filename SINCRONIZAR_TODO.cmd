@echo off
setlocal
echo === 1/2: Publicando el codigo actual en Fly ===
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\fly\sirius-fly.ps1" deploy
if errorlevel 1 (
  echo.
  echo No se pudo publicar el codigo en Fly. Revisa el mensaje anterior.
  pause
  exit /b 1
)
echo.
echo === 2/2: Sincronizando fuentes, simulando localmente y publicando resultados ===
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\simulate-and-publish.ps1" %*
if errorlevel 1 (
  echo.
  echo No se pudo completar la simulacion local. Revisa el mensaje anterior.
  pause
  exit /b 1
)
echo.
echo Listo: codigo publicado, fuentes Sirius sincronizadas y resultados en Fly.
echo Si hay candidatos nuevos, revisalos en la pestana Sirius del dashboard antes de que cuenten como evidencia.
pause
