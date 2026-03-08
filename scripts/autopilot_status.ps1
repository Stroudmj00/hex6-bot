param(
    [string]$RepoPath = "C:\Hexagonal tic tac toe",
    [string]$RunDir = ""
)

$ErrorActionPreference = "Stop"

$repoResolved = (Resolve-Path $RepoPath).Path
$autopilotRoot = Join-Path $repoResolved "artifacts\autopilot"
$daemonRoot = Join-Path $autopilotRoot "daemon"
$daemonLockPath = Join-Path $daemonRoot "daemon_lock.json"
$daemonStatePath = Join-Path $daemonRoot "daemon_state.json"
$startupLauncher = "C:\Users\Admin\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\hex6_autopilot_watchdog.cmd"

Write-Output "Repo path: $repoResolved"
Write-Output "Autopilot root: $autopilotRoot"
Write-Output ""

if (Test-Path $daemonLockPath) {
    try {
        $daemonLock = Get-Content -Raw $daemonLockPath | ConvertFrom-Json
        $daemonProc = Get-Process -Id $daemonLock.pid -ErrorAction SilentlyContinue
        Write-Output "Daemon lock: present"
        Write-Output "Daemon pid: $($daemonLock.pid)"
        Write-Output "Daemon state: $(if ($null -eq $daemonProc) { 'not running (stale lock?)' } else { 'running' })"
    }
    catch {
        Write-Output "Daemon lock: present but unreadable"
    }
}
else {
    Write-Output "Daemon lock: not present"
}

if (Test-Path $daemonStatePath) {
    Write-Output ""
    Write-Output "--- Daemon state ---"
    Get-Content -Path $daemonStatePath
}

Write-Output ""
Write-Output "Startup launcher: $(if (Test-Path $startupLauncher) { $startupLauncher } else { 'not installed' })"

Write-Output ""
Write-Output "--- Scheduler tasks ---"
foreach ($taskName in @("Codex_Hex6_Autopilot_Watchdog", "Codex_Hex6_Autopilot_Tick", "Codex_Hex6_Hourly_Checkin")) {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $taskOutput = & schtasks /Query /TN $taskName /V /FO LIST 2>$null
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($exitCode -eq 0) {
        $taskOutput
        Write-Output ""
    }
}

if ([string]::IsNullOrWhiteSpace($RunDir)) {
    $latest = Get-ChildItem -Path $autopilotRoot -Directory -Filter "run-*" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -eq $latest) {
        throw "No autopilot runs found under $autopilotRoot"
    }
    $RunDir = $latest.FullName
}

$metaPath = Join-Path $RunDir "run.json"
$eventsPath = Join-Path $RunDir "events.jsonl"
$stderrPath = Join-Path $RunDir "stderr.log"
$lastMessagePath = Join-Path $RunDir "last_message.txt"

if (!(Test-Path $metaPath)) {
    throw "Missing run metadata: $metaPath"
}

$meta = Get-Content -Raw $metaPath | ConvertFrom-Json
$process = Get-Process -Id $meta.pid -ErrorAction SilentlyContinue

Write-Output "--- Latest run ---"
Write-Output "Run ID: $($meta.run_id)"
Write-Output "Run dir: $RunDir"
Write-Output "PID: $($meta.pid)"
Write-Output "Process state: $(if ($null -eq $process) { 'not running' } else { 'running' })"
Write-Output "Events path: $eventsPath"
Write-Output "Stderr path: $stderrPath"
Write-Output "Last message path: $lastMessagePath"

if (Test-Path $eventsPath) {
    Write-Output ""
    Write-Output "--- Recent events tail ---"
    Get-Content -Path $eventsPath -Tail 20
}

if (Test-Path $stderrPath) {
    Write-Output ""
    Write-Output "--- Stderr tail ---"
    Get-Content -Path $stderrPath -Tail 20
}

if (Test-Path $lastMessagePath) {
    Write-Output ""
    Write-Output "--- Last message preview ---"
    Get-Content -Path $lastMessagePath -TotalCount 40
}
