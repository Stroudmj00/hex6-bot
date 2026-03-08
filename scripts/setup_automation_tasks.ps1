param(
    [string]$RepoPath = "C:\Hexagonal tic tac toe",
    [string]$WatchConfigPath = "configs/colab.toml",
    [string]$RunId = "latest",
    [string]$StatusBackend = "github_branch",
    [string]$WebConfigPath = "configs/play.toml",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

$repoResolved = (Resolve-Path $RepoPath).Path
$startupDir = [Environment]::GetFolderPath("Startup")
$logDir = Join-Path $repoResolved "artifacts\local_ops"
$watchScript = Join-Path $repoResolved "scripts\start_colab_status_watch.ps1"
$webScript = Join-Path $repoResolved "scripts\start_local_web_app.ps1"
$disableHeavyScript = Join-Path $repoResolved "scripts\stop_local_heavy_jobs.ps1"
$watchLauncher = Join-Path $startupDir "hex6_colab_status_watch.cmd"
$webLauncher = Join-Path $startupDir "hex6_local_web_app.cmd"
$watchLog = Join-Path $logDir "colab_status_watch.log"
$webLog = Join-Path $logDir "local_web_app.log"

foreach ($requiredPath in @($watchScript, $webScript, $disableHeavyScript)) {
    if (!(Test-Path $requiredPath)) {
        throw "Required script not found: $requiredPath"
    }
}

if (!(Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

& powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $disableHeavyScript -RepoPath $repoResolved

$watchBody = @"
@echo off
setlocal
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$watchScript" -RepoPath "$repoResolved" -ConfigPath "$WatchConfigPath" -RunId "$RunId" -StatusBackend "$StatusBackend" >> "$watchLog" 2>&1
exit /b 0
"@

$webBody = @"
@echo off
setlocal
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$webScript" -RepoPath "$repoResolved" -ConfigPath "$WebConfigPath" -BindHost "$BindHost" -Port $Port >> "$webLog" 2>&1
exit /b 0
"@

Set-Content -Path $watchLauncher -Value $watchBody -Encoding ascii
Set-Content -Path $webLauncher -Value $webBody -Encoding ascii

& powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $watchScript `
    -RepoPath $repoResolved `
    -ConfigPath $WatchConfigPath `
    -RunId $RunId `
    -StatusBackend $StatusBackend

& powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $webScript `
    -RepoPath $repoResolved `
    -ConfigPath $WebConfigPath `
    -BindHost $BindHost `
    -Port $Port

Write-Output "Startup launcher installed: $watchLauncher"
Write-Output "Startup launcher installed: $webLauncher"
Write-Output "Logs: $logDir"
Write-Output "Legacy heavy local jobs were disabled; this PC now keeps only Colab status watching and the local web app."
