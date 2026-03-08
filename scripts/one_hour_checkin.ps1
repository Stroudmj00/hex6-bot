param(
    [string]$RepoPath = "C:\Hexagonal tic tac toe",
    [string]$BaselinePath = "",
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

if ([string]::IsNullOrWhiteSpace($BaselinePath)) {
    $BaselinePath = Join-Path $RepoPath "artifacts\checkins\baseline.json"
}

if (!(Test-Path $BaselinePath)) {
    throw "Baseline file not found: $BaselinePath"
}

$baseline = Get-Content -Raw $BaselinePath | ConvertFrom-Json
$startUtc = [DateTime]::Parse($baseline.start_utc).ToUniversalTime()
$endUtc = (Get-Date).ToUniversalTime()

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $RepoPath "artifacts\checkins\checkin-$timestamp.md"
}

$outputDir = Split-Path -Parent $OutputPath
if (!(Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

Push-Location $RepoPath
try {
    $gitStatus = git -c core.safecrlf=false status --short 2>$null
    $gitLog = git -c core.safecrlf=false log --since="$($startUtc.ToString("o"))" --pretty=format:"- %h %ad %s (%an)" --date=iso-strict 2>$null
    $gitDiffNames = git -c core.safecrlf=false diff --name-status 2>$null
    $gitDiffStat = git -c core.safecrlf=false diff --stat 2>$null
}
finally {
    Pop-Location
}

$lines = @()
$lines += "# One-Hour Codex Check-In"
$lines += ""
$lines += "- Repo: $RepoPath"
$lines += "- Start (UTC): $($startUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))"
$lines += "- End (UTC): $($endUtc.ToString("yyyy-MM-ddTHH:mm:ssZ"))"
$lines += ""
$lines += "## Commits In Window"
$lines += ""
if ([string]::IsNullOrWhiteSpace(($gitLog -join "`n").Trim())) {
    $lines += "- none"
}
else {
    $lines += $gitLog
}
$lines += ""
$lines += "## Working Tree Changes"
$lines += ""
if ([string]::IsNullOrWhiteSpace(($gitStatus -join "`n").Trim())) {
    $lines += "- clean"
}
else {
    $lines += '```text'
    $lines += $gitStatus
    $lines += '```'
}
$lines += ""
$lines += "## File-Level Diff (Name Status)"
$lines += ""
if ([string]::IsNullOrWhiteSpace(($gitDiffNames -join "`n").Trim())) {
    $lines += "- none"
}
else {
    $lines += '```text'
    $lines += $gitDiffNames
    $lines += '```'
}
$lines += ""
$lines += "## Diff Stat"
$lines += ""
if ([string]::IsNullOrWhiteSpace(($gitDiffStat -join "`n").Trim())) {
    $lines += "- none"
}
else {
    $lines += '```text'
    $lines += $gitDiffStat
    $lines += '```'
}

$lines -join "`n" | Set-Content -Path $OutputPath -Encoding ascii
Write-Output "Wrote check-in report: $OutputPath"
