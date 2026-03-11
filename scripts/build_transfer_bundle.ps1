param(
    [string]$RepoPath = "C:\Hexagonal tic tac toe",
    [string]$OutputDir = "C:\Hexagonal tic tac toe\artifacts\transfer"
)

$ErrorActionPreference = "Stop"

$repo = Resolve-Path $RepoPath
$gitHead = git -C $repo rev-parse --short HEAD
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outputRoot = New-Item -ItemType Directory -Force -Path $OutputDir
$zipPath = Join-Path $outputRoot.FullName "hex6-colab-bundle-$timestamp-$gitHead.zip"

git -C $repo archive --format=zip --output="$zipPath" HEAD

Write-Output $zipPath
