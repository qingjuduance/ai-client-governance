[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TargetProjectPath,
    [string]$RulesRepoPath = $PSScriptRoot,
    [string]$EmbedPath = ".codex\ai-rules",
    [string]$RemoteUrl,
    [ValidateSet("clone", "submodule")]
    [string]$Mode = "submodule",
    [string]$Branch,
    [switch]$NoBackup,
    [switch]$SkipRootEntry,
    [switch]$SkipProjectPlaceholder
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RulesRepoPath)) {
    $RulesRepoPath = Split-Path -Parent $MyInvocation.MyCommand.Path
}

function Resolve-RequiredPath {
    param([string]$Path)
    return (Resolve-Path -LiteralPath $Path).Path
}

function Join-ProjectPath {
    param([string]$RelativePath)
    return Join-Path $TargetProjectPath $RelativePath
}

function Write-Utf8NoBomFile {
    param([string]$Path, [string]$Content)

    $encoding = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Backup-ExistingFile {
    param([string]$TargetPath, [string]$RelativeTarget, [string]$BackupRoot)

    if (-not (Test-Path -LiteralPath $TargetPath)) {
        return
    }
    if ($NoBackup) {
        Remove-Item -LiteralPath $TargetPath -Force
        return
    }
    $backup = Join-Path $BackupRoot $RelativeTarget
    New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
    Move-Item -LiteralPath $TargetPath -Destination $backup -Force
}

function Write-GeneratedFile {
    param(
        [string]$RelativePath,
        [string]$Content,
        [string]$BackupRoot,
        [switch]$OnlyIfMissing
    )

    $target = Join-ProjectPath -RelativePath $RelativePath
    if (Test-Path -LiteralPath $target) {
        if ($OnlyIfMissing) {
            return
        }
        $existing = Get-Content -LiteralPath $target -Raw -Encoding UTF8
        if ($existing.TrimEnd() -eq $Content.TrimEnd()) {
            return
        }
        Backup-ExistingFile -TargetPath $target -RelativeTarget $RelativePath -BackupRoot $BackupRoot
    }

    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Write-Utf8NoBomFile -Path $target -Content $Content
}

function Invoke-Git {
    param(
        [string]$WorkingDirectory,
        [string[]]$GitArgs
    )

    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & git -C $WorkingDirectory @GitArgs 2>&1
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $oldPreference
    if ($exitCode -ne 0) {
        throw "git -C $WorkingDirectory $($GitArgs -join ' ') failed with exit code $exitCode`n$($output -join "`n")"
    }
    if ($output) {
        $output | Write-Host
    }
}

function Test-GitSubmoduleRegistered {
    param([string]$WorkingDirectory, [string]$RelativePath)

    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & git -C $WorkingDirectory ls-files --stage -- $RelativePath 2>$null
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $oldPreference
    if ($exitCode -ne 0 -or -not $output) {
        return $false
    }
    return (($output -join "`n") -match "^160000\s")
}

function Test-GitWorkTree {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & git -C $Path rev-parse --is-inside-work-tree 2>$null
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $oldPreference
    return $exitCode -eq 0 -and (($output -join "").Trim() -eq "true")
}

function Get-RootAgentsContent {
    $lines = @(
        '# AI Rules Entry',
        '',
        '## Read Order',
        '',
        'This file is a thin entrypoint. Before working in this project, read:',
        '',
        '1. `.codex/ai-rules/AGENTS.md`',
        '2. `.codex/rules/project/AGENTS.md`',
        '',
        'If `.codex/ai-rules/` is missing, read `.codex/ai-rules-config.json`,',
        'locate the configured ai-rules repository, embed it at `.codex/ai-rules/`,',
        'then restart the read order.',
        '',
        '## Encoding',
        '',
        'On Windows/PowerShell, read rule files with explicit UTF-8. Set',
        '`$OutputEncoding = [System.Text.UTF8Encoding]::new()` and',
        '`[Console]::InputEncoding/OutputEncoding` to UTF-8 in the command scope,',
        'then use `Get-Content -Encoding UTF8` or',
        '`Get-Content -Raw -Encoding UTF8`.',
        '',
        '## Boundaries',
        '',
        '- `.codex/ai-rules/` is the embedded common rules Git repository.',
        '- Git projects should register it as a submodule so the parent project',
        '  records the exact ai-rules commit.',
        '- `.codex/rules/project/` belongs to this project only.',
        '- Do not write project-specific rules back to the common ai-rules repo.',
        '- Before each new session, run `.codex/ai-rules/check-ai-rules-sync.ps1`',
        '  or an equivalent wrapper and warn until the embedded repo is synchronized.'
    )
    return ($lines -join [Environment]::NewLine)
}

function Get-ProjectRulesPlaceholder {
    $lines = @(
        '# Project-Specific Rules',
        '',
        '## Scope',
        '',
        '- This file records only this project''s specific rules.',
        '- Common AI collaboration rules live in `.codex/ai-rules/AGENTS.md`.',
        '- Do not write project-specific rules back to the common `ai-rules` repo.',
        '- Add local directory, business, documentation, source snapshot, runtime,',
        '  deliverable, and maintenance requirements here or in nearby Markdown files.'
    )
    return ($lines -join [Environment]::NewLine)
}

$TargetProjectPath = Resolve-RequiredPath -Path $TargetProjectPath
$RulesRepoPath = Resolve-RequiredPath -Path $RulesRepoPath

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git is not available in PATH"
}

$embedTarget = if ([System.IO.Path]::IsPathRooted($EmbedPath)) {
    $EmbedPath
}
else {
    Join-ProjectPath -RelativePath $EmbedPath
}
$embedParent = Split-Path -Parent $embedTarget
New-Item -ItemType Directory -Path $embedParent -Force | Out-Null

$source = if (-not [string]::IsNullOrWhiteSpace($RemoteUrl)) { $RemoteUrl } else { $RulesRepoPath }
$relativeEmbed = $EmbedPath.Replace("\", "/")

if (Test-Path -LiteralPath $embedTarget) {
    if (-not (Test-GitWorkTree -Path $embedTarget)) {
        throw "Embed path exists but is not a Git work tree: $embedTarget"
    }
    if ($Mode -eq "submodule") {
        if (-not (Test-GitWorkTree -Path $TargetProjectPath)) {
            throw "Submodule mode requires target project to be a Git work tree."
        }
        if (-not (Test-GitSubmoduleRegistered -WorkingDirectory $TargetProjectPath -RelativePath $relativeEmbed)) {
            Invoke-Git -WorkingDirectory $TargetProjectPath -GitArgs @("submodule", "add", "--force", $source, $relativeEmbed)
        }
    }
    Write-Host "Embedded ai-rules repo already exists: $embedTarget"
}
elseif ($Mode -eq "submodule") {
    if (-not (Test-GitWorkTree -Path $TargetProjectPath)) {
        throw "Submodule mode requires target project to be a Git work tree."
    }
    $args = @("submodule", "add")
    if (-not [string]::IsNullOrWhiteSpace($Branch)) {
        $args += @("-b", $Branch)
    }
    $args += @($source, $relativeEmbed)
    Invoke-Git -WorkingDirectory $TargetProjectPath -GitArgs $args
}
else {
    $args = @("clone")
    if (-not [string]::IsNullOrWhiteSpace($Branch)) {
        $args += @("-b", $Branch)
    }
    $args += @($source, $embedTarget)
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & git @args 2>&1
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $oldPreference
    if ($exitCode -ne 0) {
        throw "git $($args -join ' ') failed with exit code $exitCode`n$($output -join "`n")"
    }
    if ($output) {
        $output | Write-Host
    }
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $TargetProjectPath ".codex\ai-rules-backups\$timestamp"

if (-not $SkipRootEntry) {
    Write-GeneratedFile -RelativePath "AGENTS.md" -Content (Get-RootAgentsContent) -BackupRoot $backupRoot
}
if (-not $SkipProjectPlaceholder) {
    Write-GeneratedFile -RelativePath ".codex\rules\project\AGENTS.md" -Content (Get-ProjectRulesPlaceholder) -BackupRoot $backupRoot -OnlyIfMissing
}

$configDir = Join-Path $TargetProjectPath ".codex"
New-Item -ItemType Directory -Path $configDir -Force | Out-Null
$config = [ordered]@{
    schema_version = 3
    mode = if ($Mode -eq "submodule") { "git-submodule" } else { "nested-git-clone" }
    distributionMode = "embedded-git-repository"
    installedAt = (Get-Date).ToUniversalTime().ToString("o")
    sourceRepoPath = $RulesRepoPath
    embeddedRepoPath = $EmbedPath.Replace("\", "/")
    commonEntry = ".codex/ai-rules/AGENTS.md"
    projectEntry = ".codex/rules/project/AGENTS.md"
    legacyCommonEntry = ".codex/rules/common/AGENTS.md"
    syncPolicy = [ordered]@{
        checkEverySession = $true
        fetchIntervalHours = 24
        warnUntilSynced = $true
        autoFetch = $true
        autoPull = $false
        autoPush = $false
        remote = "origin"
    }
    boundaries = [ordered]@{
        commonRulesSource = ".codex/ai-rules/"
        projectRulesSource = ".codex/rules/project/"
        copyManagedPaths = $false
        parentTracksEmbeddedCommit = ($Mode -eq "submodule")
    }
}
Write-Utf8NoBomFile -Path (Join-Path $configDir "ai-rules-config.json") -Content ($config | ConvertTo-Json -Depth 8)

Write-Host "AI rules embedded into $TargetProjectPath"
Write-Host "Embedded repo: $EmbedPath"
Write-Host "Common entry: .codex/ai-rules/AGENTS.md"
Write-Host "Project entry: .codex/rules/project/AGENTS.md"
if (-not $NoBackup) {
    Write-Host "Changed generated files, if any, were backed up under $backupRoot"
}
