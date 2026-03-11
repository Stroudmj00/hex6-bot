param(
    [string]$Config = "configs/fast.toml",
    [string]$Output = "artifacts/bootstrap_fast_tracked_smoke",
    [string]$Project = "hex6-bot",
    [string]$Tags = "local,offline,smoke"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$localOps = Join-Path $repoRoot "artifacts\local_ops"
$wandbDir = Join-Path $repoRoot "artifacts\wandb"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stdout = Join-Path $localOps "bootstrap_fast_tracked_$stamp.stdout.log"
$stderr = Join-Path $localOps "bootstrap_fast_tracked_$stamp.stderr.log"

New-Item -ItemType Directory -Force -Path $localOps, $wandbDir, (Join-Path $repoRoot $Output) | Out-Null

$env:HEX6_ENABLE_WANDB = "1"
$env:HEX6_WANDB_MODE = "offline"
$env:HEX6_WANDB_PROJECT = $Project
$env:HEX6_WANDB_TAGS = $Tags
$env:WANDB_DIR = $wandbDir

$process = Start-Process `
    -FilePath $python `
    -ArgumentList "-m", "hex6.train.run_bootstrap", "--config", $Config, "--output", $Output `
    -WorkingDirectory $repoRoot `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru

[pscustomobject]@{
    pid = $process.Id
    output = (Join-Path $repoRoot $Output)
    stdout = $stdout
    stderr = $stderr
    wandb_dir = $wandbDir
} | ConvertTo-Json -Depth 3
