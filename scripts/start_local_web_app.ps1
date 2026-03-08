param(
    [string]$RepoPath = "C:\Hexagonal tic tac toe",
    [string]$ConfigPath = "configs/play.toml",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 5000,
    [switch]$Foreground
)

$ErrorActionPreference = "Stop"

$repoResolved = (Resolve-Path $RepoPath).Path
$pythonExe = Join-Path $repoResolved ".venv\Scripts\python.exe"
$logDir = Join-Path $repoResolved "artifacts\local_ops"
$stdoutPath = Join-Path $logDir "local_web_app.stdout.log"
$stderrPath = Join-Path $logDir "local_web_app.stderr.log"
if (!(Test-Path $pythonExe)) {
    $pythonExe = "python"
}
if (!(Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$existing = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -eq "python.exe" -and
        $_.CommandLine -like "*hex6.web.run_server*" -and
        $_.CommandLine -like "*--host $BindHost*" -and
        $_.CommandLine -like "*--port $Port*"
    } |
    Select-Object -First 1

if ($null -ne $existing) {
    Write-Output "Local web app already running (pid=$($existing.ProcessId))."
    exit 0
}

if ($Foreground) {
    Push-Location $repoResolved
    try {
        & $pythonExe -m hex6.web.run_server --config $ConfigPath --host $BindHost --port $Port
        if ($LASTEXITCODE -ne 0) {
            throw "run_server exited with code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
    exit 0
}

$arguments = @(
    "-m", "hex6.web.run_server",
    "--config", $ConfigPath,
    "--host", $BindHost,
    "--port", "$Port"
)
$proc = Start-Process -FilePath $pythonExe -ArgumentList $arguments -WorkingDirectory $repoResolved `
    -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
Write-Output "Started local web app (pid=$($proc.Id))."
Write-Output "Logs: $stdoutPath"
