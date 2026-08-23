[CmdletBinding()]
param(
    [ValidateSet("deploy", "pause", "resume", "status", "open", "logs")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$configPath = Join-Path $repoRoot "fly.toml"
$config = Get-Content -LiteralPath $configPath -Raw
$appMatch = [regex]::Match($config, '(?m)^app\s*=\s*"([^"]+)"')
$regionMatch = [regex]::Match($config, '(?m)^primary_region\s*=\s*"([^"]+)"')
if (-not $appMatch.Success -or -not $regionMatch.Success) {
    throw "No se pudo leer app/primary_region desde fly.toml."
}
$appName = $appMatch.Groups[1].Value
$region = $regionMatch.Groups[1].Value

$fly = Get-Command flyctl -ErrorAction SilentlyContinue
if (-not $fly) {
    $candidate = Join-Path $env:USERPROFILE ".fly\bin\flyctl.exe"
    if (Test-Path -LiteralPath $candidate) {
        $fly = Get-Item -LiteralPath $candidate
    } else {
        throw "Falta flyctl. Instalalo desde https://fly.io/docs/flyctl/install/"
    }
}

function Invoke-Fly {
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $fly.Source @args
        $flyExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if ($flyExitCode -ne 0) {
        throw "flyctl terminó con código $flyExitCode."
    }
}

function Get-FlyJson {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [switch]$AllowFailure
    )

    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $json = & $fly.Source @Arguments 2>$null
        $flyExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if ($flyExitCode -ne 0) {
        if ($AllowFailure) { return $null }
        throw "flyctl terminó con código $flyExitCode al solicitar JSON."
    }
    if (-not $json) { return $null }
    return $json | ConvertFrom-Json
}

function Get-Machines {
    return @(Get-FlyJson -Arguments @("machine", "list", "--app", $appName, "--json") -AllowFailure)
}

Set-Location -LiteralPath $repoRoot

switch ($Action) {
    "deploy" {
        Invoke-Fly auth whoami | Out-Null
        $apps = Get-FlyJson -Arguments @("apps", "list", "--json")
        if (-not ($apps | Where-Object { $_.Name -eq $appName })) {
            Invoke-Fly apps create $appName --org personal
        }

        $volumes = Get-FlyJson -Arguments @("volumes", "list", "--app", $appName, "--json")
        if (-not ($volumes | Where-Object { $_.Name -eq "sirius_data" })) {
            Invoke-Fly volumes create sirius_data --app $appName --region $region `
                --size 5 --snapshot-retention 7 --yes
        }

        $localEnv = Join-Path $repoRoot ".env"
        if (-not (Test-Path -LiteralPath $localEnv)) {
            Copy-Item -LiteralPath (Join-Path $repoRoot ".env.example") -Destination $localEnv
        }
        $envContent = Get-Content -LiteralPath $localEnv -Raw
        $apiKeyMatch = [regex]::Match($envContent, '(?m)^SIRIUS_API_KEY=(.*)$')
        $apiKey = if ($apiKeyMatch.Success) { $apiKeyMatch.Groups[1].Value.Trim() } else { $null }
        if ([string]::IsNullOrWhiteSpace($apiKey) -or $apiKey -like "replace-*") {
            $bytes = New-Object byte[] 32
            [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
            $apiKey = [Convert]::ToHexString($bytes).ToLowerInvariant()
            if ($apiKeyMatch.Success) {
                $envContent = [regex]::Replace(
                    $envContent,
                    '(?m)^SIRIUS_API_KEY=.*$',
                    "SIRIUS_API_KEY=$apiKey"
                )
            }
            else {
                $envContent = $envContent.TrimEnd() + [Environment]::NewLine + `
                    "SIRIUS_API_KEY=$apiKey" + [Environment]::NewLine
            }
            [System.IO.File]::WriteAllText($localEnv, $envContent)
        }
        Invoke-Fly secrets set --app $appName --stage "SIRIUS_API_KEY=$apiKey"
        $apiKey = $null

        Invoke-Fly config validate --config $configPath --strict
        $codeStateJson = & python -c "import json; from services.api.update_pipeline import _git_state; print(json.dumps(_git_state()))"
        if ($LASTEXITCODE -ne 0 -or -not $codeStateJson) {
            throw "No se pudo calcular la trazabilidad del código a publicar."
        }
        $codeState = $codeStateJson | ConvertFrom-Json
        $workingTreeHash = if ($codeState.working_tree_sha256) {
            $codeState.working_tree_sha256
        } else {
            ""
        }
        Invoke-Fly deploy --config $configPath --ha=false --strategy immediate --yes `
            --build-arg "SIRIUS_GIT_COMMIT=$($codeState.git_commit)" `
            --build-arg "SIRIUS_GIT_DIRTY=$($codeState.git_dirty.ToString().ToLowerInvariant())" `
            --build-arg "SIRIUS_WORKING_TREE_SHA256=$workingTreeHash"

        foreach ($machine in Get-Machines) {
            # An immediate deploy preserves a stopped machine's state. Start it
            # explicitly so the health check validates the newly published image.
            if ($machine.state -ne "started") {
                Invoke-Fly machine start $machine.id --app $appName
            }
            Invoke-Fly machine wait $machine.id --app $appName --state started --wait-timeout 5m
        }
        $healthy = $false
        foreach ($attempt in 1..60) {
            $checksByMachine = Get-FlyJson `
                -Arguments @("checks", "list", "--app", $appName, "--json") `
                -AllowFailure
            if ($checksByMachine) {
                $checks = @(
                    $checksByMachine.PSObject.Properties |
                        ForEach-Object { $_.Value } |
                        ForEach-Object { $_ }
                )
                if ($checks.Count -gt 0 -and -not ($checks | Where-Object { $_.status -ne "passing" })) {
                    $healthy = $true
                    break
                }
            }
            Start-Sleep -Seconds 2
        }
        if (-not $healthy) {
            throw "La publicación terminó, pero el health check no quedó en verde."
        }
        Invoke-Fly status --app $appName
        Write-Host "Sirius quedó publicado en https://$appName.fly.dev"
    }
    "pause" {
        foreach ($machine in Get-Machines) {
            if ($machine.state -notin @("stopped", "suspended")) {
                Invoke-Fly machine stop $machine.id --app $appName --signal SIGTERM --timeout 300
                Invoke-Fly machine wait $machine.id --app $appName --state stopped --wait-timeout 5m
            }
        }
        Write-Host "Sirius está pausado. Una visita al sitio puede despertarlo automáticamente."
    }
    "resume" {
        foreach ($machine in Get-Machines) {
            if ($machine.state -ne "started") {
                Invoke-Fly machine start $machine.id --app $appName
            }
        }
        Write-Host "Sirius está iniciando en https://$appName.fly.dev"
    }
    "status" { Invoke-Fly status --app $appName }
    "open" { Invoke-Fly open --app $appName }
    "logs" { Invoke-Fly logs --app $appName }
}
