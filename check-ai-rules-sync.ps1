[CmdletBinding()]
param(
    [string]$TargetProjectPath = (Get-Location).Path,
    [string]$EmbeddedRepoPath,
    [string]$ConfigPath,
    [int]$FetchIntervalHours = 24,
    [string]$RemoteName = "origin",
    [switch]$ForceFetch,
    [switch]$NoFetch,
    [switch]$FailOnWarning
)

$ErrorActionPreference = "Stop"

function Resolve-ProjectPath {
    param([string]$Path)
    return (Resolve-Path -LiteralPath $Path).Path
}

function Convert-ToProjectRelative {
    param([string]$Path, [string]$ProjectPath)

    $full = [System.IO.Path]::GetFullPath($Path)
    $root = [System.IO.Path]::GetFullPath($ProjectPath).TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
    if ($full.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $full.Substring($root.Length).Replace("\", "/")
    }
    return $full
}

function Read-JsonFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    return Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Write-Utf8NoBomFile {
    param([string]$Path, [string]$Content)

    $encoding = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Write-State {
    param(
        [string]$Path,
        [object]$PreviousState,
        [bool]$Fetched,
        [string]$Status
    )

    $now = (Get-Date).ToUniversalTime().ToString("o")
    $data = [ordered]@{
        schema_version = 3
        last_checked_at = $now
        last_fetch_at = if ($Fetched) { $now } elseif ($PreviousState -and $PreviousState.last_fetch_at) { $PreviousState.last_fetch_at } else { $null }
        last_status = $Status
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force | Out-Null
    Write-Utf8NoBomFile -Path $Path -Content ($data | ConvertTo-Json -Depth 8)
}

function Invoke-GitText {
    param(
        [string]$RepoPath,
        [string[]]$GitArgs,
        [switch]$ThrowOnError
    )

    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & git -C $RepoPath @GitArgs 2>&1
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $oldPreference
    $text = ($output -join "`n").Trim()
    if ($ThrowOnError -and $exitCode -ne 0) {
        throw "git $($GitArgs -join ' ') failed with exit code $exitCode`n$text"
    }
    return [pscustomobject]@{
        ExitCode = $exitCode
        Text = $text
    }
}

function Add-Warning {
    param([System.Collections.Generic.List[string]]$Warnings, [string]$Message)
    $Warnings.Add($Message) | Out-Null
    Write-Warning $Message
}

function Test-FetchDue {
    param($State, [int]$Hours)

    if ($ForceFetch) {
        return $true
    }
    if ($NoFetch) {
        return $false
    }
    if ($null -eq $State -or -not $State.last_fetch_at) {
        return $true
    }
    $lastFetch = ([datetime]$State.last_fetch_at).ToUniversalTime()
    return ((Get-Date).ToUniversalTime() - $lastFetch).TotalHours -ge $Hours
}

$TargetProjectPath = Resolve-ProjectPath -Path $TargetProjectPath
if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $ConfigPath = Join-Path $TargetProjectPath ".codex\ai-rules-config.json"
}
elseif (-not [System.IO.Path]::IsPathRooted($ConfigPath)) {
    $ConfigPath = Join-Path $TargetProjectPath $ConfigPath
}

$config = Read-JsonFile -Path $ConfigPath
if ([string]::IsNullOrWhiteSpace($EmbeddedRepoPath)) {
    if ($config -and $config.embeddedRepoPath) {
        $EmbeddedRepoPath = $config.embeddedRepoPath
    }
    else {
        $EmbeddedRepoPath = ".codex\ai-rules"
    }
}
if (-not [System.IO.Path]::IsPathRooted($EmbeddedRepoPath)) {
    $EmbeddedRepoPath = Join-Path $TargetProjectPath $EmbeddedRepoPath
}

$warnings = [System.Collections.Generic.List[string]]::new()
$notes = [System.Collections.Generic.List[string]]::new()
$statePath = Join-Path $TargetProjectPath ".codex\ai-rules-state.json"
$state = Read-JsonFile -Path $statePath
$repoLabel = Convert-ToProjectRelative -Path $EmbeddedRepoPath -ProjectPath $TargetProjectPath

if (-not (Test-Path -LiteralPath $EmbeddedRepoPath)) {
    Add-Warning -Warnings $warnings -Message "Embedded ai-rules repo is missing at $repoLabel. Embed it before rule work."
    Write-State -Path $statePath -PreviousState $state -Fetched:$false -Status "missing"
    if ($FailOnWarning) { exit 1 }
    exit 0
}

$inside = Invoke-GitText -RepoPath $EmbeddedRepoPath -GitArgs @("rev-parse", "--is-inside-work-tree")
if ($inside.ExitCode -ne 0 -or $inside.Text -ne "true") {
    Add-Warning -Warnings $warnings -Message "$repoLabel exists but is not a Git work tree."
    Write-State -Path $statePath -PreviousState $state -Fetched:$false -Status "not-git"
    if ($FailOnWarning) { exit 1 }
    exit 0
}

$remote = Invoke-GitText -RepoPath $EmbeddedRepoPath -GitArgs @("remote", "get-url", $RemoteName)
$remotePresent = $remote.ExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace($remote.Text)
$fetched = $false

if ($remotePresent -and (Test-FetchDue -State $state -Hours $FetchIntervalHours)) {
    $fetch = Invoke-GitText -RepoPath $EmbeddedRepoPath -GitArgs @("fetch", $RemoteName)
    if ($fetch.ExitCode -eq 0) {
        $fetched = $true
        $notes.Add("Fetched $RemoteName for $repoLabel.") | Out-Null
    }
    else {
        Add-Warning -Warnings $warnings -Message "Could not fetch $RemoteName for $repoLabel. $($fetch.Text)"
    }
}
elseif ($remotePresent) {
    $notes.Add("Fetch skipped: last fetch is within $FetchIntervalHours hours.") | Out-Null
}
else {
    Add-Warning -Warnings $warnings -Message "$repoLabel has no remote named $RemoteName; update checks can only inspect local state."
}

$status = Invoke-GitText -RepoPath $EmbeddedRepoPath -GitArgs @("status", "--porcelain")
if (-not [string]::IsNullOrWhiteSpace($status.Text)) {
    Add-Warning -Warnings $warnings -Message "$repoLabel has local uncommitted changes. Commit, stash, or discard intentionally before syncing."
}

$branch = Invoke-GitText -RepoPath $EmbeddedRepoPath -GitArgs @("branch", "--show-current")
if ([string]::IsNullOrWhiteSpace($branch.Text)) {
    Add-Warning -Warnings $warnings -Message "$repoLabel is in detached HEAD state; record the intended ai-rules version explicitly."
}
else {
    $upstream = Invoke-GitText -RepoPath $EmbeddedRepoPath -GitArgs @("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    $upstreamName = $upstream.Text
    if ($upstream.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($upstreamName)) {
        if ($remotePresent) {
            $candidate = "$RemoteName/$($branch.Text)"
            $verify = Invoke-GitText -RepoPath $EmbeddedRepoPath -GitArgs @("rev-parse", "--verify", $candidate)
            if ($verify.ExitCode -eq 0) {
                $upstreamName = $candidate
            }
        }
    }

    if ([string]::IsNullOrWhiteSpace($upstreamName)) {
        Add-Warning -Warnings $warnings -Message "$repoLabel branch '$($branch.Text)' has no upstream; compare or push manually."
    }
    else {
        $counts = Invoke-GitText -RepoPath $EmbeddedRepoPath -GitArgs @("rev-list", "--left-right", "--count", "HEAD...$upstreamName")
        if ($counts.ExitCode -eq 0) {
            $parts = $counts.Text -split "\s+"
            $ahead = [int]$parts[0]
            $behind = [int]$parts[1]
            if ($ahead -gt 0 -and $behind -gt 0) {
                Add-Warning -Warnings $warnings -Message "$repoLabel diverged from $upstreamName (ahead $ahead, behind $behind). Resolve manually."
            }
            elseif ($ahead -gt 0) {
                Add-Warning -Warnings $warnings -Message "$repoLabel is ahead of $upstreamName by $ahead commit(s). Push from .codex/ai-rules when approved."
            }
            elseif ($behind -gt 0) {
                Add-Warning -Warnings $warnings -Message "$repoLabel is behind $upstreamName by $behind commit(s). Run git pull --ff-only inside .codex/ai-rules."
            }
            else {
                $notes.Add("$repoLabel is aligned with $upstreamName.") | Out-Null
            }
        }
        else {
            Add-Warning -Warnings $warnings -Message "Could not compare $repoLabel with $upstreamName. $($counts.Text)"
        }
    }
}

$finalStatus = if ($warnings.Count -eq 0) { "ok" } else { "warning" }
Write-State -Path $statePath -PreviousState $state -Fetched:$fetched -Status $finalStatus

Write-Host "AI rules sync check: $finalStatus"
foreach ($note in $notes) {
    Write-Host "- $note"
}
if ($warnings.Count -gt 0) {
    Write-Host "Warnings repeat every session until the embedded ai-rules repository is synchronized."
}

if ($FailOnWarning -and $warnings.Count -gt 0) {
    exit 1
}
