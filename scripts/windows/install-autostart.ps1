[CmdletBinding()]
param([switch]$Remove)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$startScript = Join-Path $projectRoot "scripts\windows\start-sirius.ps1"
$startupDirectory = [Environment]::GetFolderPath("Startup")
$launcherPath = Join-Path $startupDirectory "Mundial 2030 Sirius Engine.vbs"

if ($Remove) {
    if (Test-Path -LiteralPath $launcherPath) {
        Remove-Item -LiteralPath $launcherPath -Force
        Write-Host "Autoinicio de Sirius eliminado." -ForegroundColor Yellow
    }
    else {
        Write-Host "El autoinicio de Sirius no estaba instalado."
    }
    return
}

$powerShellCommand = 'powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -NoBrowser -NoBuild' -f $startScript
$escapedCommand = $powerShellCommand.Replace('"', '""')
$launcher = @"
Set shell = CreateObject("WScript.Shell")
shell.Run "$escapedCommand", 0, False
"@

$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($launcherPath, $launcher, $utf8WithoutBom)
Write-Host "Autoinicio instalado para tu sesion de Windows." -ForegroundColor Green
Write-Host "Docker y Sirius se iniciaran automaticamente al ingresar."
Write-Host "Para revertirlo, ejecuta QUITAR_AUTOINICIO_SIRIUS.cmd."
