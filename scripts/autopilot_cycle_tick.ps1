param(
    [string]$RepoPath = "C:\Hexagonal tic tac toe",
    [int]$DurationMinutes = 60,
    [int]$CooldownMinutes = 10,
    [int]$MaxRunMinutes = 120,
    [string]$Profile = "yolo",
    [string]$StatePath = ""
)

$ErrorActionPreference = "Stop"

$repoResolved = (Resolve-Path $RepoPath).Path
$autopilotRoot = Join-Path $repoResolved "artifacts\autopilot"
if ([string]::IsNullOrWhiteSpace($StatePath)) {
    $StatePath = Join-Path $autopilotRoot "supervisor_state.json"
}

if (!(Test-Path $autopilotRoot)) {
    New-Item -ItemType Directory -Path $autopilotRoot -Force | Out-Null
}

function Read-State([string]$path) {
    if (Test-Path $path) {
        return (Get-Content -Raw $path | ConvertFrom-Json)
    }
    return [pscustomobject]@{
        active_run_id = ""
        last_run_start_utc = ""
        last_run_end_utc = ""
        last_completed_run_id = ""
        next_allowed_start_utc = ""
        last_tick_utc = ""
    }
}

function Write-State([string]$path, [object]$state) {
    $state | ConvertTo-Json | Set-Content -Path $path -Encoding ascii
}

function Get-RunMetas([string]$root) {
    $metas = @()
    $runDirs = Get-ChildItem -Path $root -Directory -Filter "run-*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending
    foreach ($dir in $runDirs) {
        $metaPath = Join-Path $dir.FullName "run.json"
        if (!(Test-Path $metaPath)) {
            continue
        }
        try {
            $meta = Get-Content -Raw $metaPath | ConvertFrom-Json
            $meta | Add-Member -NotePropertyName run_dir -NotePropertyValue $dir.FullName -Force
            $metas += $meta
        }
        catch {
            continue
        }
    }
    return $metas
}

function Is-RunActive([object]$meta) {
    if ($null -eq $meta) {
        return $false
    }
    if ($null -eq $meta.pid) {
        return $false
    }
    $proc = Get-Process -Id $meta.pid -ErrorAction SilentlyContinue
    return $null -ne $proc
}

$state = Read-State $StatePath
$now = Get-Date
$nowUtc = $now.ToUniversalTime()

$metas = Get-RunMetas $autopilotRoot
$activeMeta = $null
foreach ($meta in $metas) {
    if (Is-RunActive $meta) {
        $activeMeta = $meta
        break
    }
}

if ($null -ne $activeMeta) {
    $runStartUtc = $null
    try {
        if (![string]::IsNullOrWhiteSpace($activeMeta.started_utc)) {
            $runStartUtc = [DateTime]::Parse($activeMeta.started_utc).ToUniversalTime()
        }
    }
    catch {
        $runStartUtc = $null
    }
    if ($null -eq $runStartUtc) {
        $procStart = Get-Process -Id $activeMeta.pid -ErrorAction SilentlyContinue
        if ($null -ne $procStart) {
            $runStartUtc = $procStart.StartTime.ToUniversalTime()
        }
    }

    if ($MaxRunMinutes -gt 0 -and $null -ne $runStartUtc) {
        $elapsedMinutes = ($nowUtc - $runStartUtc).TotalMinutes
        if ($elapsedMinutes -gt $MaxRunMinutes) {
            Stop-Process -Id $activeMeta.pid -Force -ErrorAction SilentlyContinue
            $state.last_completed_run_id = $activeMeta.run_id
            $state.last_run_end_utc = $nowUtc.ToString("o")
            $state.active_run_id = ""
            $state.last_tick_utc = $nowUtc.ToString("o")
            $state.next_allowed_start_utc = $nowUtc.AddMinutes($CooldownMinutes).ToString("o")
            Write-State $StatePath $state
            Write-Output "Terminated stale run $($activeMeta.run_id) after $([Math]::Round($elapsedMinutes,1)) minutes; cooldown now active."
            exit 0
        }
    }

    $state.active_run_id = $activeMeta.run_id
    if ([string]::IsNullOrWhiteSpace($state.last_run_start_utc) -or $state.active_run_id -ne $state.last_completed_run_id) {
        $state.last_run_start_utc = $activeMeta.started_utc
    }
    $state.last_tick_utc = $nowUtc.ToString("o")
    Write-State $StatePath $state
    Write-Output "Run in progress: $($activeMeta.run_id) (pid=$($activeMeta.pid)); no new run started."
    exit 0
}

if (![string]::IsNullOrWhiteSpace($state.active_run_id)) {
    $state.last_completed_run_id = $state.active_run_id
    $state.last_run_end_utc = $nowUtc.ToString("o")
    $state.active_run_id = ""
}

$cooldownAnchor = $null
if (![string]::IsNullOrWhiteSpace($state.last_run_end_utc)) {
    $cooldownAnchor = [DateTime]::Parse($state.last_run_end_utc).ToUniversalTime()
}
elseif ($metas.Count -gt 0) {
    # Unknown end time for existing completed runs; anchor cooldown to this tick.
    $cooldownAnchor = $nowUtc
    $state.last_run_end_utc = $cooldownAnchor.ToString("o")
}

if ($null -ne $cooldownAnchor) {
    $nextAllowed = $cooldownAnchor.AddMinutes($CooldownMinutes)
    $state.next_allowed_start_utc = $nextAllowed.ToString("o")
    if ($nowUtc -lt $nextAllowed) {
        $state.last_tick_utc = $nowUtc.ToString("o")
        Write-State $StatePath $state
        Write-Output "Cooldown active until $($nextAllowed.ToString('yyyy-MM-ddTHH:mm:ssZ')); no new run started."
        exit 0
    }
}

$startScript = Join-Path $repoResolved "scripts\start_yolo_autopilot.ps1"
if (!(Test-Path $startScript)) {
    throw "Start script not found: $startScript"
}

$output = & powershell -NoProfile -ExecutionPolicy Bypass -File $startScript `
    -RepoPath $repoResolved `
    -DurationMinutes $DurationMinutes `
    -Profile $Profile 2>&1

$runId = ""
foreach ($line in $output) {
    if ($line -match "^Run ID:\s*(\S+)\s*$") {
        $runId = $Matches[1]
    }
}

if ([string]::IsNullOrWhiteSpace($runId)) {
    $latestAfterStart = Get-RunMetas $autopilotRoot | Select-Object -First 1
    if ($null -ne $latestAfterStart) {
        $runId = $latestAfterStart.run_id
    }
}

$state.active_run_id = $runId
$state.last_run_start_utc = $nowUtc.ToString("o")
$state.last_tick_utc = $nowUtc.ToString("o")
$state.next_allowed_start_utc = ""
Write-State $StatePath $state

Write-Output ($output -join "`n")
Write-Output "Autopilot tick started run: $runId"
