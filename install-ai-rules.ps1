[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TargetProjectPath,
    [switch]$SkipSync,
    [switch]$NoBackup,
    [bool]$AutoRefresh = $true
)

$ErrorActionPreference = "Stop"
$RulesRepoPath = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($RulesRepoPath)) {
    $RulesRepoPath = Split-Path -Parent $MyInvocation.MyCommand.Path
}
$TargetProjectPath = (Resolve-Path -LiteralPath $TargetProjectPath).Path

function Copy-ManagedPath {
    param([string]$RelativePath, [string]$BackupRoot)

    $source = Join-Path $RulesRepoPath $RelativePath
    $target = Join-Path $TargetProjectPath $RelativePath
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Missing managed path in rules repo: $RelativePath"
    }

    if (Test-Path -LiteralPath $target) {
        if (-not $NoBackup) {
            $backup = Join-Path $BackupRoot $RelativePath
            New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
            Move-Item -LiteralPath $target -Destination $backup -Force
        }
        else {
            Remove-Item -LiteralPath $target -Recurse -Force
        }
    }

    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Recurse -Force
}

if (-not $SkipSync) {
    $checkScript = Join-Path $RulesRepoPath "check-ai-rules-sync.ps1"
    & powershell -ExecutionPolicy Bypass -File $checkScript -RulesRepoPath $RulesRepoPath -TargetProjectPath $TargetProjectPath -NoInstallRefresh
    if ($LASTEXITCODE -ne 0) {
        throw "AI rules pre-install sync failed with exit code $LASTEXITCODE"
    }
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $TargetProjectPath ".codex\ai-rules-backups\$timestamp"

$managedPaths = @(
    "AGENTS.md",
    ".codex\skills\agents-rule-maintainer",
    ".codex\skills\locate-pasted-content",
    ".codex\skills\self-correction-planner",
    "scripts\agent_comm.py",
    "scripts\agent_group_status.py",
    "scripts\scan_corrections.py",
    "scripts\scan_markdown_compliance.py",
    "docs\_meta\agent-collaboration.md",
    "check-ai-rules-sync.ps1"
)

foreach ($path in $managedPaths) {
    Copy-ManagedPath -RelativePath $path -BackupRoot $backupRoot
}

$configDir = Join-Path $TargetProjectPath ".codex"
New-Item -ItemType Directory -Path $configDir -Force | Out-Null
$config = [ordered]@{
    rulesRepoPath = $RulesRepoPath
    installedAt = (Get-Date).ToUniversalTime().ToString("o")
    autoRefresh = $AutoRefresh
    managedPaths = $managedPaths
}
$config | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $configDir "ai-rules-config.json") -Encoding UTF8

Write-Host "AI rules installed into $TargetProjectPath"
if (-not $NoBackup) {
    Write-Host "Existing managed files, if any, were backed up under $backupRoot"
}
