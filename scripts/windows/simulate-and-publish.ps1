[CmdletBinding()]
param(
    [ValidateSet(48, 64)]
    [int]$FormatSize = 64,
    [ValidateRange(100, 1000000)]
    [int]$Iterations = 100000,
    [ValidateRange(1, 64)]
    [int]$Workers = [Math]::Max(1, [Environment]::ProcessorCount - 1),
    [ValidateSet(17, 18, 20, 21)]
    [int]$FinalHour = 18,
    [switch]$NoUpload
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$virtualEnvironment = Join-Path $projectRoot ".venv-sirius-local-py312"
$python = Join-Path $virtualEnvironment "Scripts\python.exe"

Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath $python)) {
        $launcher = Get-Command py -ErrorAction SilentlyContinue
        if ($launcher) {
            $previousErrorAction = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            try {
                & $launcher.Source -V:3.12 -c "import sys" 2>$null
                $hasPython312 = $LASTEXITCODE -eq 0
            }
            finally {
                $ErrorActionPreference = $previousErrorAction
            }
            if (-not $hasPython312) {
                Write-Host "Instalando Python 3.12 compatible con Swiss Ephemeris..." -ForegroundColor Cyan
                & $launcher.Source install -y 3.12
                if ($LASTEXITCODE -ne 0) {
                    throw "No se pudo instalar Python 3.12."
                }
            }
            & $launcher.Source -V:3.12 -m venv $virtualEnvironment
        }
        else {
            $systemPython = Get-Command python -ErrorAction SilentlyContinue
            if (-not $systemPython) {
                throw "Falta Python 3.11 o superior."
            }
            & $systemPython.Source -c `
                "import sys; assert sys.version_info[:2] == (3, 12)"
            if ($LASTEXITCODE -ne 0) {
                throw "Se necesita Python 3.12 para Swiss Ephemeris en Windows."
            }
            & $systemPython.Source -m venv $virtualEnvironment
        }
        if ($LASTEXITCODE -ne 0) {
            throw "No se pudo crear .venv."
        }
    }

    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $python -c "import requests, pandas, fastapi, sqlalchemy, swisseph" 2>$null
        $dependenciesInstalled = $LASTEXITCODE -eq 0
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if (-not $dependenciesInstalled) {
        Write-Host "Instalando dependencias locales por unica vez..." -ForegroundColor Cyan
        & $python -m pip install -e .
        if ($LASTEXITCODE -ne 0) {
            throw "No se pudieron instalar las dependencias."
        }
    }
    & $python -c `
        "import sys, swisseph; assert sys.version_info[:2] == (3, 12)"
    if ($LASTEXITCODE -ne 0) {
        throw "El entorno local no puede ejecutar Swiss Ephemeris de forma confiable."
    }

    Write-Host "Simulacion local: $FormatSize equipos, $Iterations iteraciones, $Workers workers." -ForegroundColor Cyan
    $simulationArguments = @(
        "scripts/simulate_local_and_publish.py",
        "--format-size", $FormatSize,
        "--iterations", $Iterations,
        "--workers", $Workers,
        "--final-hour", $FinalHour
    )
    if ($NoUpload) {
        $simulationArguments += "--no-upload"
    }
    & $python @simulationArguments
    if ($LASTEXITCODE -ne 0) {
        throw "La simulacion o publicacion termino con codigo $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
