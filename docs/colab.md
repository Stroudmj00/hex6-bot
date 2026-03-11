# Colab Setup

## Goal

Run the same guided-MCTS AlphaZero-style training loop on Colab so GPU-backed training and
local development use the same configs and artifact format.

## Operating policy

- local machine: code editing, unit tests, CPU-only debug/profiling, and web/debug work
- do not use the local GPU for experimental training or evaluation
- Colab: all real training runs, pipeline comparisons, longer evals, and efficiency experiments
- long runs should prefer the queue/automation path so results and status land in the same place every time

## GPU policy

Standard Colab cannot guarantee a specific GPU model on every runtime. The practical way to avoid wasting long runs is:

- request a GPU runtime in Colab
- inspect the detected GPU before launching the job
- fail fast unless it meets a minimum tier you accept

This repo now supports that directly through `scripts/colab_run.py`.

Supported tiers:

- `H100`
- `A100`
- `V100`
- `A10G`
- `L4`
- `T4`
- `P100`
- `K80`

For this repo, a reasonable policy is:

- long training runs: `--minimum-gpu-tier V100`
- okay-but-cheaper fallback: `--minimum-gpu-tier T4`
- highest-end only: `--minimum-gpu-tier A100`

Default project policy:

- regular Colab cycle/eval runs: `V100+`
- strongest-model pushes: `A100` only

## What I need from you

I do not need your Google password or any browser cookie copied into chat.

To wire up Colab cleanly, I only need:

- the Google account email you use for Colab
- the Google Colab notebook URL you want the extension or automation to open
- the local Google Drive sync root used by Colab Desktop sync
- the repo mirror path under that Drive root
- whether GitHub status publishing should be enabled

Optional but useful:

- confirmation that the `HEX6_GITHUB_TOKEN` Colab secret exists
- confirmation that the VS Code Colab extension is already signed in

Once those are set, I can fill the repo-side pieces myself:

- `trainingFilePath`
- `resultsSavePath`
- the exact `python -m ...` command for the job type
- whether the run should be a one-shot cycle, queue loop, or targeted eval

## What the Colab lane does

- runs `guided_mcts` self-play
- trains from visit-distribution policy targets plus final outcome values
- keeps the bounded `15 x 15` rules from the repo defaults
- writes `progress.json`, `metrics.json`, checkpoints, and tournament summaries
- can publish status back to the `colab-status` branch
- promotes challengers through a stronger promotion lane with baseline included

## Primary configs

- `configs/fast.toml`: fast smoke lane
- `configs/colab.toml`: medium lane
- `configs/colab_hour.toml`: repeated cycle lane
- `configs/colab_strongest_v2.toml`: best current Colab training lane
- `configs/colab_job_queue.toml`: priority-queue automation

## Recommended commands

Bootstrap run:

```bash
python -m hex6.train.run_bootstrap --config configs/colab.toml --output artifacts/bootstrap_colab
```

Cycle run:

```bash
python -m hex6.train.run_cycle --config configs/colab_strongest_v2.toml --output-root artifacts/bootstrap_colab_strongest_v2 --minutes 60
```

Tournament eval:

```bash
python -m hex6.eval.run_tournament --config configs/fast.toml --output artifacts/tournament_colab --games-per-match 4 --max-game-plies 0 --opening-suite configs/experiments/opening_suite.toml --max-checkpoints 3 --checkpoint-glob "artifacts/**/bootstrap_model.pt" --include-baseline --include-random --run-id <run-id> --status-backend github_branch
```

Priority queue:

```bash
python -m hex6.integration.run_priority_loop --queue configs/colab_job_queue.toml --state artifacts/colab_queue/state.json --status-backend github_branch
```

## Recommended split

Use this split unless there is a specific reason not to:

- local
  - `.venv\Scripts\python -m pytest`
  - `.venv\Scripts\python -m hex6.web.run_server --config configs/play.toml --host 127.0.0.1 --port 5000`
  - CPU-only smoke/debug commands when needed
- Colab
  - `python -m hex6.train.run_cycle --config configs/colab_strongest_v2.toml --output-root artifacts/bootstrap_colab_strongest_v2 --minutes 60`
  - `python -m hex6.integration.run_priority_loop --queue configs/colab_job_queue.toml --state artifacts/colab_queue/state.json --status-backend github_branch`
  - `python scripts/colab_run.py runtime-benchmark --repo-root /content/drive/MyDrive/Hex-A-Toe --minimum-gpu-tier V100 --config configs/colab_strongest_v2.toml --output artifacts/runtime_parallelism_colab`
  - long tournament, board-size ablation, and efficiency runs

## Notebook recipe

If your Drive mirror lives at `/content/drive/MyDrive/Hex-A-Toe`, this is the cleanest notebook flow.

Cell 1: mount Drive and enter the repo

```python
from google.colab import drive
drive.mount("/content/drive")
%cd /content/drive/MyDrive/Hex-A-Toe
```

Cell 2: install the repo and confirm CUDA

```bash
python -m pip install -U pip
python -m pip install -e .[dev]
python - <<'PY'
import torch
print("cuda_available =", torch.cuda.is_available())
print("device_count =", torch.cuda.device_count())
print("device_name =", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu")
PY
```

Cell 3: optional GitHub status secret

```python
import os
try:
    from google.colab import userdata
    token = userdata.get("HEX6_GITHUB_TOKEN")
    if token:
        os.environ["HEX6_GITHUB_TOKEN"] = token
        print("Loaded HEX6_GITHUB_TOKEN from Colab secrets.")
    else:
        print("No HEX6_GITHUB_TOKEN secret found.")
except Exception as exc:
    print(f"Could not load Colab secret: {exc}")
```

Cell 4: optional W&B tracking

```python
import os
os.environ["HEX6_ENABLE_WANDB"] = "1"
os.environ["HEX6_WANDB_MODE"] = "online"  # use "offline" if you only want local files on Drive
os.environ["HEX6_WANDB_PROJECT"] = "hex6-bot"
os.environ["HEX6_WANDB_TAGS"] = "colab,cycle"
os.environ["WANDB_DIR"] = "/content/drive/MyDrive/Hex-A-Toe/artifacts/wandb"
```

Cell 5: run a one-hour cycle

```bash
python scripts/colab_run.py cycle \
  --repo-root /content/drive/MyDrive/Hex-A-Toe \
  --minimum-gpu-tier V100 \
  --config configs/colab_strongest_v2.toml \
  --output-root artifacts/bootstrap_colab_strongest_v2 \
  --minutes 60
```

Cell 6: run the always-on priority queue instead

```bash
python scripts/colab_run.py queue \
  --repo-root /content/drive/MyDrive/Hex-A-Toe \
  --minimum-gpu-tier V100 \
  --queue configs/colab_job_queue.toml \
  --state artifacts/colab_queue/state.json \
  --max-minutes 480
```

Cell 7: runtime benchmark / efficiency sweep

```bash
python scripts/colab_run.py runtime-benchmark \
  --repo-root /content/drive/MyDrive/Hex-A-Toe \
  --minimum-gpu-tier V100 \
  --config configs/colab_strongest_v2.toml \
  --output artifacts/runtime_parallelism_colab \
  --cpu-threads 8 \
  --interop-threads 2 \
  --self-play-workers 4 8 12 \
  --data-loader-workers 2 \
  --parallel-expansions-per-root 4 6 8 \
  --root-simulations 96 \
  --bootstrap-games 2 \
  --epochs 1 \
  --max-game-plies 0
```

Cell 8: targeted tournament eval

```bash
python scripts/colab_run.py tournament \
  --repo-root /content/drive/MyDrive/Hex-A-Toe \
  --minimum-gpu-tier V100 \
  --config configs/fast.toml \
  --output artifacts/tournament_colab \
  --games-per-match 4 \
  --max-game-plies 0 \
  --checkpoint-glob "artifacts/**/bootstrap_model.pt" \
  --opening-suite configs/experiments/conversion_opening_suite.toml
```

## GitHub status publishing

If you want notebook runs to publish status back to GitHub, add a Colab secret named
`HEX6_GITHUB_TOKEN` with `Contents: Read and write` access to `Stroudmj00/hex6-bot`.

Without the secret, training still runs normally; only status publishing is disabled.

## W&B tracking

W&B tracking is now built into `hex6.train.run_bootstrap` and `hex6.train.run_cycle`.
It is opt-in and controlled only by environment variables:

- `HEX6_ENABLE_WANDB=1`
- `HEX6_WANDB_MODE=online|offline|disabled`
- `HEX6_WANDB_PROJECT=<project>`
- `HEX6_WANDB_ENTITY=<entity>`
- `HEX6_WANDB_GROUP=<group>`
- `HEX6_WANDB_TAGS=tag1,tag2`
- `HEX6_WANDB_RUN_NAME=<name>`
- `WANDB_DIR=<artifact dir>`

For Colab, set `WANDB_DIR` to a Drive-backed folder so offline runs and logs persist.

## Current guidance

- keep one training job per runtime
- use `colab_strongest_v2.toml` for the main training lane
- use `colab_efficiency_queue.toml` when the goal is to benchmark runtime ideas on Colab
- keep `colab_hour.toml` around as the previous baseline lane for controlled A/B comparisons
- keep the post-train opening-suite tournament gate fixed
- compare champions through the promotion match, not by raw loss curves alone
- if a run is expected to exceed 20 minutes, move it to Colab instead of local
- if your repo folder is still under `/content/Hex-A-Toe`, move it into `/content/drive/MyDrive/Hex-A-Toe` before long runs so checkpoints actually persist
- if the runtime comes up on a weak GPU, reject it immediately with `--minimum-gpu-tier` rather than burning the session
