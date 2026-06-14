[CmdletBinding()]
param(
    [string]$RulesRepoPath,
    [string]$TargetProjectPath = (Get-Location).Path,
    [int]$IntervalHours = 24,
    [switch]$Force,
    [switch]$NoInstallRefresh
)

$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($ScriptDir)) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

function Resolve-RulesRepoPath {
    if (-not [string]::IsNullOrWhiteSpace($RulesRepoPath)) {
        return (Resolve-Path -LiteralPath $RulesRepoPath).Path
    }

    $scriptManifest = Join-Path $ScriptDir "manifest.json"
    if (Test-Path -LiteralPath $scriptManifest) {
        return $ScriptDir
    }

    $configPath = Join-Path $TargetProjectPath ".codex\ai-rules-config.json"
    if (Test-Path -LiteralPath $configPath) {
        $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($config.rulesRepoPath) {
            return (Resolve-Path -LiteralPath $config.rulesRepoPath).Path
        }
    }

    throw "Cannot locate rules repo. Pass -RulesRepoPath or install rules first."
}

function Get-State {
    param([string]$RepoPath)
    $statePath = Join-Path $RepoPath ".ai-rules-sync\state.json"
    if (-not (Test-Path -LiteralPath $statePath)) {
        return $null
    }
    return Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Test-Due {
    param($State, [int]$Hours)
    if ($Force -or $null -eq $State) {
        return $true
    }

    $candidates = @()
    if ($State.last_sync_at) { $candidates += [datetime]$State.last_sync_at }
    if ($State.last_push_at) { $candidates += [datetime]$State.last_push_at }
    if ($candidates.Count -eq 0) {
        return $true
    }

    $oldest = ($candidates | Sort-Object | Select-Object -First 1).ToUniversalTime()
    return ((Get-Date).ToUniversalTime() - $oldest).TotalHours -ge $Hours
}

$repo = Resolve-RulesRepoPath
$state = Get-State -RepoPath $repo

if (-not (Test-Due -State $state -Hours $IntervalHours)) {
    Write-Host "AI rules sync skipped: last sync/push is within $IntervalHours hours."
    return
}

$syncScript = Join-Path $repo "sync-ai-rules.ps1"
if (-not (Test-Path -LiteralPath $syncScript)) {
    throw "Missing sync script: $syncScript"
}

& powershell -ExecutionPolicy Bypass -File $syncScript -RulesRepoPath $repo
if ($LASTEXITCODE -ne 0) {
    throw "AI rules sync failed with exit code $LASTEXITCODE"
}

$configPath = Join-Path $TargetProjectPath ".codex\ai-rules-config.json"
if (-not $NoInstallRefresh -and (Test-Path -LiteralPath $configPath)) {
    $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($config.autoRefresh) {
        $installScript = Join-Path $repo "install-ai-rules.ps1"
        & powershell -ExecutionPolicy Bypass -File $installScript -TargetProjectPath $TargetProjectPath -SkipSync
        if ($LASTEXITCODE -ne 0) {
            throw "AI rules refresh failed with exit code $LASTEXITCODE"
        }
    }
}
