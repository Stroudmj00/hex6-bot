param(
    [string]$RepoPath = "C:\Hexagonal tic tac toe",
    [int]$TickMinutes = 10,
    [int]$CheckinMinutes = 60,
    [int]$DurationMinutes = 60,
    [int]$CooldownMinutes = 10,
    [int]$MaxRunMinutes = 120,
    [string]$Profile = "yolo",
    [int]$SleepSeconds = 15
)

$ErrorActionPreference = "Stop"

$repoResolved = (Resolve-Path $RepoPath).Path
$autopilotRoot = Join-Path $repoResolved "artifacts\autopilot"
$daemonRoot = Join-Path $autopilotRoot "daemon"
$lockPath = Join-Path $daemonRoot "daemon_lock.json"
$statePath = Join-Path $daemonRoot "daemon_state.json"
$logPath = Join-Path $daemonRoot "daemon.log"
$tickScript = Join-Path $repoResolved "scripts\autopilot_cycle_tick.ps1"
$checkinScript = Join-Path $repoResolved "scripts\hourly_checkin.ps1"

if (!(Test-Path $tickScript)) {
    throw "Tick script not found: $tickScript"
}
if (!(Test-Path $checkinScript)) {
    throw "Hourly check-in script not found: $checkinScript"
}

New-Item -ItemType Directory -Path $autopilotRoot -Force | Out-Null
New-Item -ItemType Directory -Path $daemonRoot -Force | Out-Null

function Write-Log([string]$message) {
    $line = "[{0}] {1}" -f (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK"), $message
    Add-Content -Path $logPath -Value $line -Encoding ascii
    Write-Output $line
}

function Parse-Utc([string]$value) {
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $null
    }
    try {
        return [DateTime]::Parse($value).ToUniversalTime()
    }
    catch {
        return $null
    }
}

function Read-DaemonState([string]$path) {
    if (Test-Path $path) {
        try {
            return (Get-Content -Raw $path | ConvertFrom-Json)
        }
        catch {
            # Fall back to a fresh state if parsing fails.
        }
    }
    return [pscustomobject]@{
        started_utc = ""
        heartbeat_utc = ""
        last_tick_utc = ""
        last_checkin_utc = ""
        next_tick_utc = ""
        next_checkin_utc = ""
        pid = 0
        profile = ""
        repo_path = ""
    }
}

function Write-DaemonState([string]$path, [object]$state) {
    $state | ConvertTo-Json | Set-Content -Path $path -Encoding ascii
}

function Acquire-Lock([string]$path) {
    if (Test-Path $path) {
        try {
            $existing = Get-Content -Raw $path | ConvertFrom-Json
            if ($null -ne $existing.pid) {
                $proc = Get-Process -Id $existing.pid -ErrorAction SilentlyContinue
                if ($null -ne $proc -and $existing.pid -ne $PID) {
                    Write-Log "Daemon already running with pid=$($existing.pid); exiting."
                    exit 0
                }
            }
        }
        catch {
            # Ignore malformed lock and replace it.
        }
    }

    $lock = [ordered]@{
        pid = $PID
        started_utc = (Get-Date).ToUniversalTime().ToString("o")
        repo_path = $repoResolved
        tick_minutes = $TickMinutes
        checkin_minutes = $CheckinMinutes
        duration_minutes = $DurationMinutes
        cooldown_minutes = $CooldownMinutes
        max_run_minutes = $MaxRunMinutes
        profile = $Profile
    }
    $lock | ConvertTo-Json | Set-Content -Path $path -Encoding ascii
}

function Invoke-LoggedScript([string]$name, [string]$scriptPath, [string[]]$argList) {
    Write-Log "$name start."
    try {
        $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $scriptPath @argList 2>&1
        foreach ($line in $output) {
            if ($null -ne $line) {
                Write-Log "$name> $line"
            }
        }
        Write-Log "$name complete."
    }
    catch {
        Write-Log "$name failed: $($_.Exception.Message)"
    }
}

Acquire-Lock $lockPath

$state = Read-DaemonState $statePath
$nowUtc = (Get-Date).ToUniversalTime()

$nextTickUtc = Parse-Utc $state.next_tick_utc
if ($null -eq $nextTickUtc -or $nextTickUtc -lt $nowUtc) {
    $nextTickUtc = $nowUtc
}

$nextCheckinUtc = Parse-Utc $state.next_checkin_utc
if ($null -eq $nextCheckinUtc -or $nextCheckinUtc -lt $nowUtc) {
    $nextCheckinUtc = $nowUtc.AddMinutes($CheckinMinutes)
}

$state.started_utc = $nowUtc.ToString("o")
$state.heartbeat_utc = $nowUtc.ToString("o")
$state.next_tick_utc = $nextTickUtc.ToString("o")
$state.next_checkin_utc = $nextCheckinUtc.ToString("o")
$state.pid = $PID
$state.profile = $Profile
$state.repo_path = $repoResolved
Write-DaemonState $statePath $state

Write-Log "Daemon loop started (pid=$PID, tick=$TickMinutes min, checkin=$CheckinMinutes min)."

try {
    while ($true) {
        $nowUtc = (Get-Date).ToUniversalTime()
        $didWork = $false

        if ($nowUtc -ge $nextTickUtc) {
            Invoke-LoggedScript `
                -name "tick" `
                -scriptPath $tickScript `
                -argList @(
                    "-RepoPath", $repoResolved,
                    "-DurationMinutes", "$DurationMinutes",
                    "-CooldownMinutes", "$CooldownMinutes",
                    "-MaxRunMinutes", "$MaxRunMinutes",
                    "-Profile", $Profile
                )
            $nowUtc = (Get-Date).ToUniversalTime()
            $nextTickUtc = $nowUtc.AddMinutes($TickMinutes)
            $state.last_tick_utc = $nowUtc.ToString("o")
            $state.next_tick_utc = $nextTickUtc.ToString("o")
            $didWork = $true
        }

        if ($nowUtc -ge $nextCheckinUtc) {
            Invoke-LoggedScript `
                -name "hourly_checkin" `
                -scriptPath $checkinScript `
                -argList @(
                    "-RepoPath", $repoResolved
                )
            $nowUtc = (Get-Date).ToUniversalTime()
            $nextCheckinUtc = $nowUtc.AddMinutes($CheckinMinutes)
            $state.last_checkin_utc = $nowUtc.ToString("o")
            $state.next_checkin_utc = $nextCheckinUtc.ToString("o")
            $didWork = $true
        }

        $state.heartbeat_utc = $nowUtc.ToString("o")
        if ($didWork) {
            Write-DaemonState $statePath $state
        }
        else {
            # Keep a periodic heartbeat even when idle.
            Write-DaemonState $statePath $state
        }

        Start-Sleep -Seconds $SleepSeconds
    }
}
finally {
    if (Test-Path $lockPath) {
        try {
            $lock = Get-Content -Raw $lockPath | ConvertFrom-Json
            if ($null -ne $lock -and $lock.pid -eq $PID) {
                Remove-Item -Path $lockPath -Force -ErrorAction SilentlyContinue
            }
        }
        catch {
            Remove-Item -Path $lockPath -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Log "Daemon exiting (pid=$PID)."
}
