param(
    [string]$RepoPath = "C:\Hexagonal tic tac toe",
    [string]$ConfigPath = "configs/fast.toml",
    [string]$OutputPath = "artifacts/tournament/latest",
    [int]$GamesPerMatch = 2,
    [int]$MaxGamePlies = 48,
    [int]$MaxCheckpoints = 3,
    [int]$RandomSeed = 7
)

$ErrorActionPreference = "Stop"

$repoResolved = (Resolve-Path $RepoPath).Path
$pythonExe = Join-Path $repoResolved ".venv\Scripts\python.exe"
if (!(Test-Path $pythonExe)) {
    $pythonExe = "python"
}

$resolvedOutput = if ([System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath
}
else {
    Join-Path $repoResolved $OutputPath
}
$resolvedConfig = if ([System.IO.Path]::IsPathRooted($ConfigPath)) {
    $ConfigPath
}
else {
    Join-Path $repoResolved $ConfigPath
}

Push-Location $repoResolved
try {
    & $pythonExe -m hex6.eval.run_tournament `
        --config $resolvedConfig `
        --output $resolvedOutput `
        --games-per-match $GamesPerMatch `
        --max-game-plies $MaxGamePlies `
        --max-checkpoints $MaxCheckpoints `
        --checkpoint-glob "artifacts/**/bootstrap_model.pt" `
        --include-baseline `
        --include-random `
        --random-seed $RandomSeed
    if ($LASTEXITCODE -ne 0) {
        throw "run_tournament failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

Write-Output "Tournament summary: $(Join-Path $resolvedOutput 'summary.json')"
