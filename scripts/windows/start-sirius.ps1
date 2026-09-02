[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$NoBuild,
    [ValidateRange(30, 900)]
    [int]$TimeoutSeconds = 300
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$envPath = Join-Path $projectRoot ".env"
$envTemplatePath = Join-Path $projectRoot ".env.example"
$dockerDesktopPath = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"

function New-SiriusSecret {
    param([ValidateRange(16, 128)][int]$ByteCount = 32)

    $bytes = New-Object byte[] $ByteCount
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return ([System.BitConverter]::ToString($bytes)).Replace("-", "").ToLowerInvariant()
}

function Get-DotEnvValue {
    param(
        [string]$Content,
        [string]$Name
    )

    $pattern = "(?m)^$([Regex]::Escape($Name))=(.*)$"
    $match = [Regex]::Match($Content, $pattern)
    if (-not $match.Success) {
        return $null
    }
    return $match.Groups[1].Value.Trim()
}

function Set-DotEnvValue {
    param(
        [string]$Content,
        [string]$Name,
        [string]$Value
    )

    $pattern = "(?m)^$([Regex]::Escape($Name))=.*$"
    $line = "$Name=$Value"
    if ([Regex]::IsMatch($Content, $pattern)) {
        return [Regex]::Replace($Content, $pattern, $line)
    }
    return $Content.TrimEnd() + [Environment]::NewLine + $line + [Environment]::NewLine
}

function Initialize-SiriusEnvironment {
    if (-not (Test-Path -LiteralPath $envTemplatePath)) {
        throw "No se encontro $envTemplatePath."
    }

    $created = -not (Test-Path -LiteralPath $envPath)
    $content = if ($created) {
        [IO.File]::ReadAllText($envTemplatePath)
    }
    else {
        [IO.File]::ReadAllText($envPath)
    }

    $placeholderValues = @($null, "", "change-me", "replace-with-a-long-random-secret")
    $postgresPassword = Get-DotEnvValue -Content $content -Name "POSTGRES_PASSWORD"
    if ($placeholderValues -contains $postgresPassword) {
        $postgresPassword = New-SiriusSecret
        $content = Set-DotEnvValue -Content $content -Name "POSTGRES_PASSWORD" -Value $postgresPassword
    }

    $apiKey = Get-DotEnvValue -Content $content -Name "SIRIUS_API_KEY"
    if ($placeholderValues -contains $apiKey) {
        $content = Set-DotEnvValue -Content $content -Name "SIRIUS_API_KEY" -Value (New-SiriusSecret)
    }

    $databaseUrl = Get-DotEnvValue -Content $content -Name "SIRIUS_DATABASE_URL"
    if ($created -or $databaseUrl -eq "postgresql+psycopg://sirius:change-me@postgres:5432/sirius") {
        $databaseUrl = "postgresql+psycopg://sirius:$postgresPassword@postgres:5432/sirius"
        $content = Set-DotEnvValue -Content $content -Name "SIRIUS_DATABASE_URL" -Value $databaseUrl
    }

    $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($envPath, $content, $utf8WithoutBom)
    if ($created) {
        Write-Host "Configuracion .env creada con secretos aleatorios." -ForegroundColor Green
    }
}

function Test-DockerEngine {
    $previousErrorPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "SilentlyContinue"
        & docker info 1> $null 2> $null
        $dockerExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorPreference
    }
    return $dockerExitCode -eq 0
}

function Start-DockerEngine {
    if (Test-DockerEngine) {
        return
    }
    if (-not (Test-Path -LiteralPath $dockerDesktopPath)) {
        throw "Docker Desktop no esta instalado. Descargalo desde https://www.docker.com/products/docker-desktop/"
    }

    Write-Host "Iniciando Docker Desktop..."
    if (-not (Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)) {
        Start-Process -FilePath $dockerDesktopPath -WindowStyle Hidden
    }

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Seconds 2
        if (Test-DockerEngine) {
            Write-Host "Docker esta listo." -ForegroundColor Green
            return
        }
    }
    throw "Docker no respondio dentro de $TimeoutSeconds segundos. Abri Docker Desktop y volve a intentarlo."
}

function Wait-SiriusApplication {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $api = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 5
            $web = Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 5
            if ($api.StatusCode -eq 200 -and $web.StatusCode -eq 200) {
                return
            }
        }
        catch {
            # Los servicios todavia pueden estar construyendose o migrando.
        }
        Start-Sleep -Seconds 2
    }
    throw "Sirius no quedo saludable dentro de $TimeoutSeconds segundos. Ejecuta VER_ESTADO_SIRIUS.cmd."
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "No se encontro el comando docker. Instala Docker Desktop primero."
}

Initialize-SiriusEnvironment
Start-DockerEngine

Push-Location $projectRoot
try {
    $composeArguments = @("compose", "up", "-d")
    if (-not $NoBuild) {
        $composeArguments += "--build"
    }

    Write-Host "Levantando Mundial 2030 Sirius Engine..."
    & docker @composeArguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose up termino con codigo $LASTEXITCODE."
    }

    Wait-SiriusApplication
    Write-Host ""
    Write-Host "Sirius esta funcionando." -ForegroundColor Green
    Write-Host "Dashboard: http://localhost:3000"
    Write-Host "API:       http://localhost:8000/docs"
    & docker compose ps
}
finally {
    Pop-Location
}

if (-not $NoBrowser) {
    Start-Process "http://localhost:3000"
}
