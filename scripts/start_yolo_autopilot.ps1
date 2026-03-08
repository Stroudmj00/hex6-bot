param(
    [string]$RepoPath = "C:\Hexagonal tic tac toe",
    [int]$DurationMinutes = 60,
    [string]$Profile = "yolo"
)

$ErrorActionPreference = "Stop"

$repoResolved = (Resolve-Path $RepoPath).Path
$codexExe = (Get-Command codex -ErrorAction Stop).Source
$startedAt = Get-Date
$runId = $startedAt.ToString("yyyyMMdd-HHmmss")
$runDir = Join-Path $repoResolved "artifacts\autopilot\run-$runId"
$promptPath = Join-Path $runDir "prompt.md"
$eventsPath = Join-Path $runDir "events.jsonl"
$stderrPath = Join-Path $runDir "stderr.log"
$lastMessagePath = Join-Path $runDir "last_message.txt"
$metaPath = Join-Path $runDir "run.json"

New-Item -ItemType Directory -Path $runDir -Force | Out-Null

$prompt = @"
# Autonomous Hex6 Engine Sprint

You are the orchestrator. Use multi-agent delegation to maximize product quality.

## Product Goal
Build the strongest practical engine for the hexagonal tic-tac-toe variant from:
https://www.youtube.com/watch?v=Ob6QINTMIOA&t=595s

Current repo context already assumes sparse infinite board + 6-in-a-row rules.
If any rule detail from the video conflicts with repo assumptions, update assumptions and tests coherently.

## Timebox
You have approximately $DurationMinutes minutes.

## Required delegation pattern
Use these sub-agent roles repeatedly:
- @explorer to map options and risks.
- @worker to implement smallest high-impact improvements.
- @reviewer to find regressions and missing tests.
- @monitor to run checks and summarize pass/fail.

## Success priorities (in order)
1. Correctness and rule fidelity.
2. Search strength per unit time.
3. Regression safety via tests.
4. Developer ergonomics and reproducible eval commands.

## Execution loop
1. Establish baseline:
   - run lint/tests
   - run quick engine/eval benchmark path if available
2. Choose one high-ROI improvement.
3. Implement with tests.
4. Re-measure quickly.
5. Repeat until timebox ends.

## Hard constraints
- Keep assumptions config-first where practical.
- Do not commit secrets or generated artifacts.
- Keep diffs minimal and focused.
- If blocked, record blocker and next best action.

## Final output
At the end, return:
1. What changed (files + behavior impact).
2. Verification executed with results.
3. Strength/perf signals observed.
4. Top 3 next improvements.
"@

Set-Content -Path $promptPath -Value $prompt -Encoding ascii

$argLine = "exec -p $Profile --enable multi_agent --json --output-last-message `"$lastMessagePath`" -"

$process = Start-Process -FilePath $codexExe -ArgumentList $argLine -WorkingDirectory $repoResolved `
  -RedirectStandardInput $promptPath `
  -RedirectStandardOutput $eventsPath `
  -RedirectStandardError $stderrPath `
  -PassThru

$meta = [ordered]@{
    run_id = $runId
    started_local = $startedAt.ToString("yyyy-MM-dd HH:mm:ss zzz")
    started_utc = $startedAt.ToUniversalTime().ToString("o")
    repo_path = $repoResolved
    profile = $Profile
    duration_minutes = $DurationMinutes
    pid = $process.Id
    codex_exe = $codexExe
    run_dir = $runDir
    prompt_path = $promptPath
    events_path = $eventsPath
    stderr_path = $stderrPath
    last_message_path = $lastMessagePath
}

$meta | ConvertTo-Json | Set-Content -Path $metaPath -Encoding ascii

Write-Output "Started YOLO autopilot run."
Write-Output "Run ID: $runId"
Write-Output "PID: $($process.Id)"
Write-Output "Run dir: $runDir"
Write-Output "Events: $eventsPath"
Write-Output "Last message: $lastMessagePath"
