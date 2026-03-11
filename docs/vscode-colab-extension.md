# VS Code Colab Extension Quick Start

This is the fastest way to launch Hex6 runs with the Google Colab VS Code extension.

## What this is for

Use this when you want:

- a connected Colab runtime inside VS Code
- Drive-backed checkpoints and artifacts
- the repo's standard Colab commands without hand-building cells every time

## Required files

- notebook: `notebooks/hex6_colab_vscode_launch.ipynb`
- Colab workflow: `docs/colab.md`

## One-time setup

1. Install the Google Colab VS Code extension.
2. Open `notebooks/hex6_colab_vscode_launch.ipynb`.
3. Click `Select Kernel`.
4. Choose `Colab`.
5. Sign in if prompted.
6. For a quick default connection, choose `Auto Connect`.
7. For GPU work, prefer `New Colab Server` so you can provision a specific machine type instead of inheriting the default server.

## What to run

Run the notebook cells in order:

1. mount Drive
2. ensure the repo exists in `/content/drive/MyDrive/Hex-A-Toe`
3. install the repo
4. verify the GPU
5. optional secrets / W&B
6. either:
   - strongest current cycle run
   - efficiency benchmark sweep

## Exact GPU workflow

If `Auto Connect` lands you on CPU, do this instead:

1. Open the kernel picker in the notebook.
2. Select `Colab`.
3. If a server is already attached, remove it first:
   - notebook toolbar `Colab` menu -> `Remove Server`, or
   - command palette -> `Colab: Remove Server`
4. Select `New Colab Server`.
5. Pick a GPU-capable server or machine type when prompted.
6. Re-run the GPU check cell.

For this repo:

- reject CPU runtimes
- reject weak long-run GPUs
- prefer `V100+` for normal long runs
- prefer `A100` for strongest-model pushes

## GPU rule

Reject weak runtimes. The notebook uses `scripts/colab_run.py` with:

- `--minimum-gpu-tier V100` for normal long runs

If the run exits immediately because the GPU is below the requested tier, reconnect the runtime and rerun the cell.

The repo already enforces this through `scripts/colab_run.py --minimum-gpu-tier ...`, so a weak runtime will fail fast instead of silently burning time.

## Recommended VS Code settings

The official extension exposes useful experimental features that help with troubleshooting:

- `colab.activityBar = true`
- `colab.terminal = true`
- `colab.serverMounting = true` if you want to inspect the runtime filesystem from VS Code

The Activity Bar lets you see assigned Colab servers and interact with `/content`.
The terminal feature lets you open a terminal directly on the Colab runtime.

To enable them:

1. Open VS Code settings.
2. Search for `colab`.
3. Enable the features above.
4. Reload VS Code if prompted.

## Repo freshness warning

The notebook runs whatever repo contents are currently in Drive.

If your local workspace is newer than GitHub, do one of these before a serious run:

- push the current local repo to GitHub and pull it in Colab
- copy the newer repo snapshot into Drive

## Known extension issues that matter here

Based on the official extension wiki:

- `userdata.get()` can fail in VS Code Colab sessions
  - workaround: set env vars manually in a notebook cell or use the web Colab UI to copy the secret value once
- `drive.mount()` is supported in current extension versions
- file changes made outside VS Code may not appear immediately in mounted/runtime views
  - workaround: refresh the view or reload VS Code

That means this repo's optional secret-loading cell is best-effort only. If it fails, set:

- `HEX6_GITHUB_TOKEN`
- `WANDB_API_KEY`

manually in a notebook cell before the training cell.

## CPU-only troubleshooting

If the GPU check cell prints:

- `cuda: False`
- `gpu: cpu`

work through this exact order:

1. Remove the currently assigned server.
2. Create a `New Colab Server` instead of using `Auto Connect`.
3. Pick a GPU-capable machine type.
4. Re-run the GPU check cell.
5. If it still shows CPU, disconnect and create another new server.
6. If VS Code keeps reattaching the same CPU server, open the notebook once in browser Colab, assign a GPU runtime there, then reconnect from VS Code.

## Recommended first run

Use the strongest current cycle lane first:

- config: `configs/colab_strongest_v2.toml`
- output: `artifacts/bootstrap_colab_strongest_v2`

Then use the runtime benchmark cell when the goal is throughput tuning instead of model strength.
