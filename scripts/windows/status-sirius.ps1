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
    & docker compose ps
    Write-Host ""
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 5
        Write-Host "API saludable: $($response.status)" -ForegroundColor Green
        Write-Host "Dashboard: http://localhost:3000"
    }
    catch {
        Write-Host "La API todavia no responde. Ultimos logs:" -ForegroundColor Yellow
        & docker compose logs --tail 30 api web worker
    }
}
finally {
    Pop-Location
}
