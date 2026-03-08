param(
    [string]$RepoPath = "C:\Hexagonal tic tac toe",
    [int]$TickMinutes = 10,
    [int]$CheckinMinutes = 60,
    [int]$DurationMinutes = 60,
    [int]$CooldownMinutes = 10,
    [int]$MaxRunMinutes = 120,
    [string]$Profile = "yolo"
)

$ErrorActionPreference = "Stop"

$repoResolved = (Resolve-Path $RepoPath).Path
$daemonScript = Join-Path $repoResolved "scripts\autopilot_daemon.ps1"
$autopilotRoot = Join-Path $repoResolved "artifacts\autopilot"
$daemonRoot = Join-Path $autopilotRoot "daemon"
$lockPath = Join-Path $daemonRoot "daemon_lock.json"
$launcherLogPath = Join-Path $daemonRoot "watchdog.log"
$daemonStdoutPath = Join-Path $daemonRoot "daemon_stdout.log"
$daemonStderrPath = Join-Path $daemonRoot "daemon_stderr.log"

if (!(Test-Path $daemonScript)) {
    throw "Daemon script not found: $daemonScript"
}

New-Item -ItemType Directory -Path $autopilotRoot -Force | Out-Null
New-Item -ItemType Directory -Path $daemonRoot -Force | Out-Null

function Write-Watchdog([string]$message) {
    $line = "[{0}] {1}" -f (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK"), $message
    Add-Content -Path $launcherLogPath -Value $line -Encoding ascii
}

if (Test-Path $lockPath) {
    try {
        $lock = Get-Content -Raw $lockPath | ConvertFrom-Json
        if ($null -ne $lock.pid) {
            $proc = Get-Process -Id $lock.pid -ErrorAction SilentlyContinue
            if ($null -ne $proc) {
                Write-Watchdog "Daemon already running (pid=$($lock.pid))."
                exit 0
            }
        }
        Remove-Item -Path $lockPath -Force -ErrorAction SilentlyContinue
    }
    catch {
        Remove-Item -Path $lockPath -Force -ErrorAction SilentlyContinue
    }
}

$argLine = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$daemonScript`" -RepoPath `"$repoResolved`" -TickMinutes $TickMinutes -CheckinMinutes $CheckinMinutes -DurationMinutes $DurationMinutes -CooldownMinutes $CooldownMinutes -MaxRunMinutes $MaxRunMinutes -Profile $Profile"

$proc = Start-Process -FilePath "powershell" -ArgumentList $argLine -WorkingDirectory $repoResolved `
    -WindowStyle Hidden -RedirectStandardOutput $daemonStdoutPath -RedirectStandardError $daemonStderrPath -PassThru
Write-Watchdog "Started daemon process pid=$($proc.Id)."
