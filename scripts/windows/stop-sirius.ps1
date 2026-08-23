[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "No se encontro el comando docker."
}

Push-Location $projectRoot
try {
    & docker compose stop
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudieron detener los servicios."
    }
    Write-Host "Sirius quedo detenido. Los datos se conservaron." -ForegroundColor Yellow
}
finally {
    Pop-Location
}
