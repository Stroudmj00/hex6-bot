param(
    [string]$RepoPath = "C:\Hexagonal tic tac toe",
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$repoResolved = (Resolve-Path $RepoPath).Path
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $repoResolved "docs\executive-review.md"
}

function Parse-DoubleOrNull([string]$text, [string]$pattern) {
    $match = [regex]::Match($text, $pattern)
    if (!$match.Success) {
        return $null
    }
    [double]::Parse($match.Groups[1].Value, [System.Globalization.CultureInfo]::InvariantCulture)
}

function Parse-IntOrNull([string]$text, [string]$pattern) {
    $match = [regex]::Match($text, $pattern)
    if (!$match.Success) {
        return $null
    }
    [int]$match.Groups[1].Value
}

function Round-Value($value, [int]$digits = 2) {
    if ($null -eq $value) {
        return "n/a"
    }
    return [Math]::Round([double]$value, $digits).ToString([System.Globalization.CultureInfo]::InvariantCulture)
}

function To-DoubleOrNull($value) {
    if ($null -eq $value) {
        return $null
    }
    $text = "$value"
    if ([string]::IsNullOrWhiteSpace($text)) {
        return $null
    }
    $parsed = 0.0
    if ([double]::TryParse($text, [System.Globalization.NumberStyles]::Float, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$parsed)) {
        return $parsed
    }
    if ([double]::TryParse($text, [ref]$parsed)) {
        return $parsed
    }
    return $null
}

function To-DateOrNull($value) {
    if ($null -eq $value) {
        return $null
    }
    $text = "$value"
    if ([string]::IsNullOrWhiteSpace($text)) {
        return $null
    }
    try {
        return [DateTime]::Parse($text).ToUniversalTime()
    }
    catch {
        return $null
    }
}

$autopilotRoot = Join-Path $repoResolved "artifacts\autopilot"
$latestRunDir = Get-ChildItem -Path $autopilotRoot -Directory -Filter "run-*" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

$meta = $null
$lastMessage = ""
$runState = "not_started"
$runId = "n/a"
$runStartedUtc = "n/a"
$runDuration = "n/a"

if ($null -ne $latestRunDir) {
    $metaPath = Join-Path $latestRunDir.FullName "run.json"
    $lastMessagePath = Join-Path $latestRunDir.FullName "last_message.txt"
    if (Test-Path $metaPath) {
        $meta = Get-Content -Raw $metaPath | ConvertFrom-Json
        $runId = $meta.run_id
        $runStartedUtc = $meta.started_utc
        $runDuration = "$($meta.duration_minutes) minutes"
        $process = Get-Process -Id $meta.pid -ErrorAction SilentlyContinue
        $runState = if ($null -eq $process) { "completed_or_exited" } else { "running" }
    }
    if (Test-Path $lastMessagePath) {
        $lastMessage = Get-Content -Raw $lastMessagePath
    }
}

$beforeMs = Parse-DoubleOrNull $lastMessage 'Before:\s+about\s+[^0-9]*([0-9]+(?:\.[0-9]+)?)\s*ms/call'
$afterMs = Parse-DoubleOrNull $lastMessage 'After:\s+about\s+[^0-9]*([0-9]+(?:\.[0-9]+)?)\s*ms/call'
$speedupX = Parse-DoubleOrNull $lastMessage 'Net:\s+about\s+[^0-9]*([0-9]+(?:\.[0-9]+)?)x'
$passedTests = Parse-IntOrNull $lastMessage "([0-9]+)\s+passed"

if ($null -eq $speedupX -and $null -ne $beforeMs -and $null -ne $afterMs -and $afterMs -gt 0) {
    $speedupX = $beforeMs / $afterMs
}

$opportunities = @()
if ($lastMessage -match "(?is)Top 3 Next Improvements(.*)$") {
    $tail = $Matches[1]
    $tailLines = $tail -split "`r?`n"
    foreach ($line in $tailLines) {
        $m = [regex]::Match($line.Trim(), "^\d+\.\s+(.+)$")
        if ($m.Success) {
            $opportunities += $m.Groups[1].Value.Trim()
        }
    }
}
if ($opportunities.Count -eq 0) {
    $opportunities = @(
        "Add state-signature caching across search and heuristic paths.",
        "Improve runtime dispatch so `config.search.algorithm` drives actual engine selection.",
        "Build a fast tactical benchmark path that always completes under 5 minutes."
    )
}

$eloSourcePaths = @()
$eloSourceCount = 0
$eloEntries = @()
$eloLatest = $null
$eloFiles = Get-ChildItem -Path (Join-Path $repoResolved "artifacts") -Recurse -File -Filter "elo_history.json" -ErrorAction SilentlyContinue
if ($eloFiles.Count -gt 0) {
    $dedupMap = @{}
    foreach ($file in $eloFiles) {
        try {
            $raw = Get-Content -Raw $file.FullName
            $parsed = ConvertFrom-Json $raw
            if ($null -eq $parsed) {
                continue
            }
            $arr = @($parsed)
            if ($arr.Count -le 0) {
                continue
            }
            $eloSourcePaths += $file.FullName
            foreach ($entry in $arr) {
                $tsKey = "$($entry.timestamp)"
                $gamesKey = "$($entry.games)"
                $agentAKey = if ($null -ne $entry.agent_a -and $null -ne $entry.agent_a.name) { "$($entry.agent_a.name)" } else { "n/a" }
                $agentBKey = if ($null -ne $entry.agent_b -and $null -ne $entry.agent_b.name) { "$($entry.agent_b.name)" } else { "n/a" }
                $eloKeyValue = To-DoubleOrNull $entry.final_elo_a
                $wrKeyValue = To-DoubleOrNull $entry.win_rate_a
                $eloKey = if ($null -eq $eloKeyValue) { "n/a" } else { [Math]::Round($eloKeyValue, 4).ToString([System.Globalization.CultureInfo]::InvariantCulture) }
                $wrKey = if ($null -eq $wrKeyValue) { "n/a" } else { [Math]::Round($wrKeyValue, 4).ToString([System.Globalization.CultureInfo]::InvariantCulture) }
                $entryKey = "$tsKey|$agentAKey|$agentBKey|$gamesKey|$eloKey|$wrKey"
                if (-not $dedupMap.ContainsKey($entryKey)) {
                    $dedupMap[$entryKey] = $entry
                }
            }
        }
        catch {
            continue
        }
    }
    if ($eloSourcePaths.Count -gt 0) {
        $eloSourcePaths = @($eloSourcePaths | Sort-Object -Unique)
        $eloSourceCount = $eloSourcePaths.Count
    }
    if ($dedupMap.Count -gt 0) {
        $eloEntries = @($dedupMap.Values)
        $eloEntries = @(
            $eloEntries |
                Sort-Object -Property @{Expression = { To-DateOrNull $_.timestamp }; Descending = $false}, @{Expression = { "$($_.timestamp)" }; Descending = $false}
        )
        if ($eloEntries.Count -gt 0) {
            $eloLatest = $eloEntries[-1]
        }
    }
}

$tournamentSummaryPath = Join-Path $repoResolved "artifacts\tournament\latest\summary.json"
$tournamentSummary = $null
$tournamentEntries = @()
$tournamentLeader = $null
$tournamentGeneratedUtc = ""
$tournamentRandom = $null
if (Test-Path $tournamentSummaryPath) {
    try {
        $tournamentSummary = Get-Content -Raw $tournamentSummaryPath | ConvertFrom-Json
        if ($null -ne $tournamentSummary) {
            $tournamentEntries = @($tournamentSummary.leaderboard)
            if ($tournamentEntries.Count -gt 0) {
                $tournamentLeader = $tournamentEntries[0]
            }
            $tournamentGeneratedUtc = "$($tournamentSummary.timestamp)"
            $tournamentRandom = $tournamentEntries | Where-Object { "$($_.name)" -match "^random" } | Select-Object -First 1
        }
    }
    catch {
        $tournamentSummary = $null
        $tournamentEntries = @()
        $tournamentLeader = $null
    }
}

Push-Location $repoResolved
try {
    $changedFiles = @(git -c core.safecrlf=false diff --name-only 2>$null)
    $changedCount = ($changedFiles | Where-Object { $_ -and $_.Trim() -ne "" }).Count
    $shortStat = git -c core.safecrlf=false diff --shortstat 2>$null
}
finally {
    Pop-Location
}

$insertions = Parse-IntOrNull ($shortStat -join "`n") "([0-9]+)\s+insertions?\(\+\)"
$deletions = Parse-IntOrNull ($shortStat -join "`n") "([0-9]+)\s+deletions?\(-\)"
$filesChangedStat = Parse-IntOrNull ($shortStat -join "`n") "([0-9]+)\s+files?\s+changed"

$generatedUtc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$perfBefore = if ($null -eq $beforeMs) { "n/a" } else { (Round-Value $beforeMs 2) }
$perfAfter = if ($null -eq $afterMs) { "n/a" } else { (Round-Value $afterMs 2) }
$perfSpeedup = if ($null -eq $speedupX) { "n/a" } else { ((Round-Value $speedupX 2) + "x") }
$testsCell = if ($null -eq $passedTests) { "n/a" } else { "$passedTests passed" }

$lines = @()
$lines += "# Executive Review"
$lines += ""
$lines += "- Generated (UTC): $generatedUtc"
$lines += "- Goal: strongest practical Hex6 engine for https://www.youtube.com/watch?v=Ob6QINTMIOA&t=595s"
$lines += ""
$lines += "## Snapshot"
$lines += ""
$lines += "| Metric | Value |"
$lines += "|---|---|"
$lines += "| Active run id | $runId |"
$lines += "| Run state | $runState |"
$lines += "| Run started (UTC) | $runStartedUtc |"
$lines += "| Planned run duration | $runDuration |"
$lines += "| Search latency before (ms/call) | $perfBefore |"
$lines += "| Search latency after (ms/call) | $perfAfter |"
$lines += "| Observed speedup | $perfSpeedup |"
$lines += "| Targeted validation tests | $testsCell |"
$lines += "| Working-tree changed files (current) | $changedCount |"
$lines += "| Diff shortstat | $($shortStat -join ' ') |"
if ($eloEntries.Count -gt 0) {
    $latestElo = To-DoubleOrNull $eloLatest.final_elo_a
    $latestWinRate = To-DoubleOrNull $eloLatest.win_rate_a
    $earliestTs = "$($eloEntries[0].timestamp)"
    $latestTs = "$($eloLatest.timestamp)"
    $lines += "| Elo source files | $eloSourceCount |"
    $lines += "| Elo samples available | $($eloEntries.Count) |"
    $lines += "| Latest Elo | $(if ($null -eq $latestElo) { 'n/a' } else { [Math]::Round($latestElo, 2).ToString([System.Globalization.CultureInfo]::InvariantCulture) }) |"
    $lines += "| Latest win rate | $(if ($null -eq $latestWinRate) { 'n/a' } else { [Math]::Round($latestWinRate, 3).ToString([System.Globalization.CultureInfo]::InvariantCulture) }) |"
    $lines += "| Earliest Elo timestamp (UTC) | $earliestTs |"
    $lines += "| Latest Elo timestamp (UTC) | $latestTs |"
}
if ($tournamentEntries.Count -gt 0) {
    $leaderName = "$($tournamentLeader.name)"
    $leaderPoints = Round-Value (To-DoubleOrNull $tournamentLeader.points) 3
    $lines += "| Tournament participants | $($tournamentEntries.Count) |"
    $lines += "| Tournament leader | $leaderName |"
    $lines += "| Tournament leader points | $leaderPoints |"
    if (-not [string]::IsNullOrWhiteSpace($tournamentGeneratedUtc)) {
        $lines += "| Tournament timestamp (UTC) | $tournamentGeneratedUtc |"
    }
}
$lines += ""

if ($null -ne $beforeMs -and $null -ne $afterMs) {
    $maxAxis = [Math]::Ceiling(([Math]::Max($beforeMs, $afterMs) + 50.0) / 50.0) * 50
    $lines += "## Graphs"
    $lines += ""
    $lines += '```mermaid'
    $lines += "xychart-beta"
    $lines += "title ""Baseline Turn Search Latency (ms/call)"""
    $lines += "x-axis [""Before"", ""After""]"
    $lines += "y-axis ""ms/call"" 0 --> $maxAxis"
    $lines += "bar [$([Math]::Round($beforeMs,2).ToString([System.Globalization.CultureInfo]::InvariantCulture)), $([Math]::Round($afterMs,2).ToString([System.Globalization.CultureInfo]::InvariantCulture))]"
    $lines += '```'
    $lines += ""
}

if ($null -ne $insertions -or $null -ne $deletions) {
    $ins = if ($null -eq $insertions) { 0 } else { $insertions }
    $del = if ($null -eq $deletions) { 0 } else { $deletions }
    $axisMax = [Math]::Max(10, ([Math]::Ceiling(([Math]::Max($ins, $del) + 10) / 10) * 10))
    if (-not ($lines -contains "## Graphs")) {
        $lines += "## Graphs"
        $lines += ""
    }
    $lines += '```mermaid'
    $lines += "xychart-beta"
    $lines += "title ""Current Diff Volume"""
    $lines += "x-axis [""Insertions"", ""Deletions""]"
    $lines += "y-axis ""Lines"" 0 --> $axisMax"
    $lines += "bar [$ins, $del]"
    $lines += '```'
    $lines += ""
}

if ($tournamentEntries.Count -gt 0) {
    $topTournament = @($tournamentEntries)
    if ($topTournament.Count -gt 8) {
        $topTournament = $topTournament[0..7]
    }
    $tLabels = @()
    $tPoints = @()
    foreach ($entry in $topTournament) {
        $label = "$($entry.name)".Replace('"', "'")
        $tLabels += """$label"""
        $pointVal = To-DoubleOrNull $entry.points
        if ($null -eq $pointVal) {
            $pointVal = 0.0
        }
        $tPoints += [Math]::Round($pointVal, 3).ToString([System.Globalization.CultureInfo]::InvariantCulture)
    }
    $maxPoints = @($topTournament | ForEach-Object {
            $tmp = To-DoubleOrNull $_.points
            if ($null -eq $tmp) { 0.0 } else { $tmp }
        } | Measure-Object -Maximum).Maximum
    if ($null -eq $maxPoints) {
        $maxPoints = 1.0
    }
    $pointAxis = [Math]::Ceiling(($maxPoints + 0.5) * 2) / 2
    if ($pointAxis -lt 1) {
        $pointAxis = 1
    }

    if (-not ($lines -contains "## Graphs")) {
        $lines += "## Graphs"
        $lines += ""
    }
    $lines += '```mermaid'
    $lines += "xychart-beta"
    $lines += "title ""Tournament Leaderboard Points"""
    $lines += "x-axis [$($tLabels -join ', ')]"
    $lines += "y-axis ""Points"" 0 --> $pointAxis"
    $lines += "bar [$($tPoints -join ', ')]"
    $lines += '```'
    $lines += ""
}

if ($eloEntries.Count -gt 0) {
    $graphSlice = @($eloEntries)
    if ($graphSlice.Count -gt 24) {
        $graphSlice = $graphSlice[($graphSlice.Count - 24)..($graphSlice.Count - 1)]
    }

    $labels = @()
    $eloVals = @()
    $winVals = @()
    foreach ($entry in $graphSlice) {
        $ts = To-DateOrNull $entry.timestamp
        if ($null -eq $ts) {
            $labels += """unknown"""
        }
        else {
            $labels += """$($ts.ToString('yyyy-MM-dd HH:mm\Z'))"""
        }
        $eloVal = To-DoubleOrNull $entry.final_elo_a
        if ($null -eq $eloVal) {
            $eloVal = 0.0
        }
        $eloVals += [Math]::Round($eloVal, 2).ToString([System.Globalization.CultureInfo]::InvariantCulture)
        $winVal = To-DoubleOrNull $entry.win_rate_a
        if ($null -eq $winVal) {
            $winVal = 0.0
        }
        $winVals += [Math]::Round($winVal, 3).ToString([System.Globalization.CultureInfo]::InvariantCulture)
    }

    $eloOnly = @()
    foreach ($entry in $graphSlice) {
        $tmp = To-DoubleOrNull $entry.final_elo_a
        if ($null -ne $tmp) {
            $eloOnly += $tmp
        }
    }
    if ($eloOnly.Count -eq 0) {
        $eloOnly = @(1200.0)
    }
    $eloMin = [Math]::Floor(((($eloOnly | Measure-Object -Minimum).Minimum) - 20.0) / 10.0) * 10
    $eloMax = [Math]::Ceiling(((($eloOnly | Measure-Object -Maximum).Maximum) + 20.0) / 10.0) * 10
    if ($eloMax -le $eloMin) {
        $eloMax = $eloMin + 10
    }

    if (-not ($lines -contains "## Graphs")) {
        $lines += "## Graphs"
        $lines += ""
    }
    $lines += '```mermaid'
    $lines += "xychart-beta"
    $lines += "title ""Elo Trend (All History Files, UTC)"""
    $lines += "x-axis [$($labels -join ', ')]"
    $lines += "y-axis ""Elo"" $([int]$eloMin) --> $([int]$eloMax)"
    $lines += "line [$($eloVals -join ', ')]"
    $lines += '```'
    $lines += ""

    $lines += '```mermaid'
    $lines += "xychart-beta"
    $lines += "title ""Win Rate Trend (agent_a)"""
    $lines += "x-axis [$($labels -join ', ')]"
    $lines += "y-axis ""Win rate"" 0 --> 1"
    $lines += "line [$($winVals -join ', ')]"
    $lines += '```'
    $lines += ""

    $lines += "## Elo Trend Data"
    $lines += ""
    $lines += "- Source files scanned: $eloSourceCount"
    foreach ($sourcePath in $eloSourcePaths) {
        $lines += ('- `' + $sourcePath + '`')
    }
    $lines += ""
    $lines += "| Timestamp (UTC) | Elo | Win Rate | Games | Agent A |"
    $lines += "|---|---:|---:|---:|---|"
    foreach ($entry in $graphSlice) {
        $tsText = "$($entry.timestamp)"
        $eloText = Round-Value (To-DoubleOrNull $entry.final_elo_a) 2
        $wrText = Round-Value (To-DoubleOrNull $entry.win_rate_a) 3
        $gamesText = "$($entry.games)"
        $agentText = if ($null -ne $entry.agent_a -and $null -ne $entry.agent_a.name) { "$($entry.agent_a.name)" } else { "n/a" }
        $lines += "| $tsText | $eloText | $wrText | $gamesText | $agentText |"
    }
    $lines += ""
}

if ($tournamentEntries.Count -gt 0) {
    $lines += "## Tournament Snapshot"
    $lines += ""
    $lines += ('- Summary: `' + $tournamentSummaryPath + '`')
    $lines += "| Rank | Agent | Kind | Points | Win Rate | W-L-D |"
    $lines += "|---:|---|---|---:|---:|---|"
    for ($rank = 0; $rank -lt $tournamentEntries.Count; $rank++) {
        $entry = $tournamentEntries[$rank]
        $name = "$($entry.name)"
        $kind = "$($entry.kind)"
        $points = Round-Value (To-DoubleOrNull $entry.points) 3
        $winRate = Round-Value (To-DoubleOrNull $entry.win_rate) 3
        $w = "$($entry.wins)"
        $l = "$($entry.losses)"
        $d = "$($entry.draws)"
        $lines += "| $($rank + 1) | $name | $kind | $points | $winRate | $w-$l-$d |"
    }
    $lines += ""
}

$lines += "## Strongest Strengths"
$lines += ""
if ($null -ne $speedupX) {
    $lines += "- Search candidate evaluation hot path improved by about $([Math]::Round($speedupX,2).ToString([System.Globalization.CultureInfo]::InvariantCulture))x in the latest run."
}
if ($null -ne $passedTests) {
    $lines += "- Focused engine/search regression tests passed ($passedTests total in the targeted validation slice)."
}
$lines += "- Multi-agent YOLO orchestration is running continuously with automated status/output capture."
if ($tournamentEntries.Count -gt 0) {
    $lines += "- Competitive benchmarking now includes random-opponent and multi-checkpoint tournament results."
}
$lines += ""
$lines += "## Best Opportunities"
$lines += ""
for ($i = 0; $i -lt [Math]::Min(3, $opportunities.Count); $i++) {
    $lines += "- $($opportunities[$i])"
}
$lines += ""
$lines += "## Operational Notes"
$lines += ""
$lines += '- Full `run_search_matrix` throughput is still the bottleneck in fast feedback loops.'
$lines += "- Prioritize improvements that reduce full-eval runtime while preserving tactical strength."
if ($eloEntries.Count -gt 0) {
    $lines += "- Elo history is tracked and timestamped; review file source shown above."
}
else {
    $lines += "- No Elo history file found yet under `artifacts/**/elo_history.json`; run arena/cycle eval to start trend tracking."
}
if ($tournamentEntries.Count -gt 0) {
    $lines += '- Tournament leaderboard is refreshed from `artifacts/tournament/latest/summary.json`.'
}
else {
    $lines += '- No tournament summary found yet; run `scripts/run_competitive_eval.ps1` to populate it.'
}

$outputDir = Split-Path -Parent $OutputPath
if (!(Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

$lines -join "`n" | Set-Content -Path $OutputPath -Encoding ascii
Write-Output "Wrote executive review: $OutputPath"
