# Colab Setup

## Goal

Run the same fast bootstrap flow in Google Colab so training can use a hosted GPU while the
codebase stays local-friendly.

## What is ready

- Config-selectable bootstrap CLI.
- Fast profile at `configs/fast.toml`.
- Colab notebook at `notebooks/hex6_colab_fast_bootstrap.ipynb`.

## Recommended first run

Use the fast profile first. It is intentionally small:

- no long-range islands,
- narrow candidate counts,
- shallow reply width,
- tiny model,
- one short bootstrap game,
- one epoch.

This is not the final bot. It is the shortest path to a working training loop.

## How to use in Colab

### Option 1: From GitHub

1. Push this repository to GitHub.
2. Open `notebooks/hex6_colab_fast_bootstrap.ipynb` in Colab.
3. Set `REPO_MODE = "git"` and fill in your repo URL.
4. Run the notebook cells.

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
python -m hex6.train.run_bootstrap --config configs/fast.toml --output artifacts/bootstrap_fast
```

- copies the resulting artifacts back to Drive if Drive mode is enabled.

## Current local validation

The fast profile already completed locally and produced:

- `artifacts/bootstrap_fast/bootstrap_model.pt`
- `artifacts/bootstrap_fast/metrics.json`

## Important limitation

Colab will accelerate the model training and later batched inference, but pure Python
self-play/search is still the main cost right now. The next optimization pass should reduce
search cost before we scale up training volume.

