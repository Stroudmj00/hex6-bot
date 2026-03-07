# Colab Setup

## Goal

Run the same bootstrap flow in Google Colab so training can use a hosted GPU while the
codebase stays local-friendly.

## Integration boundary

This project should assume:

- Colab is a separate runtime,
- local Codex work cannot directly inspect or control a live Colab session,
- synchronization must happen through explicit artifacts, repository commits, or Drive files.

The current bridge is:

- stdout logs in the notebook,
- `progress.json` written into the output artifact folder,
- `metrics.json` and model checkpoints saved to disk,
- `status/latest.json` plus per-run status files on the `colab-status` branch,
- optional copy-back into Google Drive.

If tighter integration is needed later, build it as an explicit file-based or API-based
bridge rather than assuming hidden shared session access.

## What is ready

- Config-selectable bootstrap CLI.
- Fast profile at `configs/fast.toml`.
- Medium profile at `configs/colab.toml`.
- Colab notebook at `notebooks/hex6_colab_fast_bootstrap.ipynb`.
- Local watcher at `python -m hex6.integration.watch_status`.

## One-time GitHub status setup

For the notebook to publish run status back into the repository, add a fine-grained GitHub
token to Colab secrets:

1. Create a fine-grained token with `Contents: Read and write` access to
   `Stroudmj00/hex6-bot`.
2. In Colab, open the secrets panel.
3. Add a secret named `HEX6_GITHUB_TOKEN`.

The token is not stored in this repository. The notebook loads it from Colab secrets at
runtime.

If the secret is absent, the notebook still runs training but disables GitHub status
publishing for that run.

## Recommended first run

Use the fast profile first if you are only checking wiring. For a real sprint run, use
`configs/colab.toml`.

The Colab profile is still intentionally conservative:

- no long-range islands,
- narrow candidate counts,
- shallow reply width,
- modest model,
- short bootstrap games,
- a few epochs.

This is not the final bot. It is the shortest path to a working training loop.

## How to use in Colab

### Option 1: From GitHub

1. Push this repository to GitHub.
2. Open `notebooks/hex6_colab_fast_bootstrap.ipynb` in Colab.
3. Set `REPO_MODE = "git"` and use `https://github.com/Stroudmj00/hex6-bot.git`.
4. Run the notebook cells.
5. In a local terminal, watch status with:

```powershell
.venv\Scripts\python -m hex6.integration.watch_status --config configs/colab.toml --run-id latest
```

### Option 2: From Google Drive

1. Upload the repository folder to Google Drive.
2. Open the notebook in Colab.
3. Set `REPO_MODE = "drive"` and point `DRIVE_REPO_PATH` at the folder.
4. Run the notebook cells.

## What the notebook does

- mounts Drive if needed,
- clones or copies the repo into `/content`,
- installs the package in editable mode,
- prints CUDA availability,
- runs:

```bash
python -m hex6.train.run_bootstrap --config configs/colab.toml --output artifacts/bootstrap_colab
```

- copies the resulting artifacts back to Drive if Drive mode is enabled.
- writes progress to `artifacts/bootstrap_colab/progress.json`.
- writes a GitHub-backed status document to the `colab-status` branch when
  `HEX6_GITHUB_TOKEN` is available.

## Current local validation

The project has already been validated locally with both a fast and a medium profile.

The medium profile produced:

- `artifacts/bootstrap_colab_test/bootstrap_model.pt`
- `artifacts/bootstrap_colab_test/metrics.json`
- `artifacts/bootstrap_colab_test/progress.json`

## Important limitation

Colab will accelerate the model training and later batched inference, but pure Python
self-play/search is still the main cost right now. The next optimization pass should reduce
search cost before we scale up training volume.
