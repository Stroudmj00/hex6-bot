param(
    [string]$RepoPath = "C:\Hexagonal tic tac toe"
)

$ErrorActionPreference = "Stop"

$repoResolved = (Resolve-Path $RepoPath).Path
$startupDir = [Environment]::GetFolderPath("Startup")
$legacyLaunchers = @(
    (Join-Path $startupDir "hex6_autopilot_watchdog.cmd")
)

foreach ($legacyTask in @("Codex_Hex6_Autopilot_Tick", "Codex_Hex6_Hourly_Checkin", "Codex_Hex6_Autopilot_Watchdog", "Codex_Hex6_Watchdog_Test", "Codex_Hex6_Test")) {
    try {
        & schtasks /End /TN $legacyTask *> $null
    }
    catch {}
    try {
        & schtasks /Delete /TN $legacyTask /F *> $null
    }
    catch {}
}

foreach ($launcher in $legacyLaunchers) {
    if (Test-Path $launcher) {
        Remove-Item -Path $launcher -Force -ErrorAction SilentlyContinue
    }
}

$allProcesses = Get-CimInstance Win32_Process
$rootProcesses = $allProcesses |
    Where-Object {
        ($_.Name -in @("cmd.exe", "powershell.exe", "python.exe")) -and (
            $_.CommandLine -like "*hex6.eval.run_search_matrix*" -or
            $_.CommandLine -like "*hex6.eval.run_tournament*" -or
            $_.CommandLine -like "*scripts\\hourly_checkin.ps1*" -or
            $_.CommandLine -like "*scripts\\run_competitive_eval.ps1*" -or
            $_.CommandLine -like "*scripts\\autopilot_cycle_tick.ps1*" -or
            $_.CommandLine -like "*scripts\\autopilot_daemon.ps1*" -or
            $_.CommandLine -like "*scripts\\ensure_autopilot_daemon.ps1*" -or
            $_.CommandLine -like "*scripts\\start_yolo_autopilot.ps1*" -or
            $_.CommandLine -like "*run_hex6_autopilot_watchdog.cmd*" -or
            $_.CommandLine -like "*hex6_watchdog_runner.ps1*"
        )
    }

$idsToStop = New-Object System.Collections.Generic.HashSet[int]

function Add-Descendants([int]$processId) {
    if (-not $idsToStop.Add($processId)) {
        return
    }
    $children = $allProcesses | Where-Object { $_.ParentProcessId -eq $processId }
    foreach ($child in $children) {
        Add-Descendants $child.ProcessId
    }
}

foreach ($process in $rootProcesses) {
    Add-Descendants $process.ProcessId
}

foreach ($processId in $idsToStop) {
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
}

Write-Output "Stopped legacy local heavy jobs and removed their startup/task hooks."
