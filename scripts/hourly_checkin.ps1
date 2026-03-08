param(
    [string]$RepoPath = "C:\Hexagonal tic tac toe"
)

$ErrorActionPreference = "Stop"

$repoResolved = (Resolve-Path $RepoPath).Path
$checkinsDir = Join-Path $repoResolved "artifacts\checkins"
$baselinePath = Join-Path $checkinsDir "baseline.json"

if (!(Test-Path $checkinsDir)) {
    New-Item -ItemType Directory -Path $checkinsDir -Force | Out-Null
}

$now = Get-Date
$nowUtc = $now.ToUniversalTime().ToString("o")
$nowLocal = $now.ToString("yyyy-MM-dd HH:mm:ss zzz")

if (!(Test-Path $baselinePath)) {
    $initial = [ordered]@{
        repo_path = $repoResolved
        start_utc = $nowUtc
        start_local = $nowLocal
    }
    $initial | ConvertTo-Json | Set-Content -Path $baselinePath -Encoding ascii
    Write-Output "Initialized baseline; first hourly report will be generated on next cycle."
    exit 0
}

$reportPath = Join-Path $checkinsDir ("checkin-{0}.md" -f ($now.ToString("yyyyMMdd-HHmmss")))

& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repoResolved "scripts\one_hour_checkin.ps1") `
    -RepoPath $repoResolved `
    -BaselinePath $baselinePath `
    -OutputPath $reportPath

try {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repoResolved "scripts\run_competitive_eval.ps1") `
        -RepoPath $repoResolved `
        -ConfigPath "configs/fast.toml" `
        -OutputPath "artifacts/tournament/latest" `
        -GamesPerMatch 2 `
        -MaxGamePlies 48 `
        -MaxCheckpoints 3 `
        -RandomSeed 7 | Out-Null
    Write-Output "Competitive eval updated: $(Join-Path $repoResolved 'artifacts\tournament\latest\summary.json')"
}
catch {
    Write-Output "Competitive eval skipped: $($_.Exception.Message)"
}

& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repoResolved "scripts\build_executive_review.ps1") `
    -RepoPath $repoResolved `
    -OutputPath (Join-Path $repoResolved "docs\executive-review.md")

$nextBaseline = [ordered]@{
    repo_path = $repoResolved
    start_utc = $nowUtc
    start_local = $nowLocal
}
$nextBaseline | ConvertTo-Json | Set-Content -Path $baselinePath -Encoding ascii

Write-Output "Hourly check-in complete."
Write-Output "Report: $reportPath"
Write-Output "Executive review: $(Join-Path $repoResolved 'docs\executive-review.md')"
