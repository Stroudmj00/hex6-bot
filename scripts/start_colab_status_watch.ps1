param(
    [string]$RepoPath = "C:\Hexagonal tic tac toe",
    [string]$ConfigPath = "configs/colab.toml",
    [string]$RunId = "latest",
    [string]$StatusBackend = "github_branch",
    [switch]$Foreground
)

$ErrorActionPreference = "Stop"

$repoResolved = (Resolve-Path $RepoPath).Path
$pythonExe = Join-Path $repoResolved ".venv\Scripts\python.exe"
$logDir = Join-Path $repoResolved "artifacts\local_ops"
$stdoutPath = Join-Path $logDir "colab_status_watch.stdout.log"
$stderrPath = Join-Path $logDir "colab_status_watch.stderr.log"
if (!(Test-Path $pythonExe)) {
    $pythonExe = "python"
}
if (!(Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

function Test-GitHubTokenAvailable() {
    if (-not [string]::IsNullOrWhiteSpace($env:HEX6_GITHUB_TOKEN)) {
        return $true
    }
    if (-not [string]::IsNullOrWhiteSpace($env:GITHUB_TOKEN)) {
        return $true
    }
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if ($null -eq $gh) {
        return $false
    }
    $output = & $gh.Source auth token 2>$null
    return $LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace(($output | Out-String).Trim())
}

$existing = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -eq "python.exe" -and
        $_.CommandLine -like "*hex6.integration.watch_status*" -and
        $_.CommandLine -like "*$ConfigPath*" -and
        $_.CommandLine -like "*$RunId*"
    } |
    Select-Object -First 1

if ($null -ne $existing) {
    Write-Output "Colab status watcher already running (pid=$($existing.ProcessId))."
    exit 0
}

if ($StatusBackend -eq "github_branch" -and -not (Test-GitHubTokenAvailable)) {
    Write-Output "GitHub token not available; Colab status watcher was not started."
    exit 0
}

$arguments = @(
    "-m", "hex6.integration.watch_status",
    "--config", $ConfigPath,
    "--run-id", $RunId,
    "--status-backend", $StatusBackend
)

if ($Foreground) {
    Push-Location $repoResolved
    try {
        & $pythonExe @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "watch_status exited with code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
    exit 0
}

$proc = Start-Process -FilePath $pythonExe -ArgumentList $arguments -WorkingDirectory $repoResolved `
    -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
Write-Output "Started Colab status watcher (pid=$($proc.Id))."
Write-Output "Logs: $stdoutPath"
