# Tooling Guide

## Core local commands

Use the local machine for tests, website work, and CPU-only debug/profiling.
Do not use the local GPU for experimental training or evaluation.
Use Colab for all real training, evaluation, and efficiency experiments.

Website:

```powershell
.venv\Scripts\python -m hex6.web.run_server --config configs/play.toml --host 127.0.0.1 --port 5000
```

Website with an explicit checkpoint:

```powershell
.venv\Scripts\python -m hex6.web.run_server --config configs/play.toml --checkpoint artifacts/bootstrap_alphazero_fast/bootstrap_model.pt --host 127.0.0.1 --port 5000
```

One-shot bootstrap training:

```powershell
.venv\Scripts\python -m hex6.train.run_bootstrap --config configs/fast.toml --output artifacts/bootstrap_fast
```

Repeated training/eval cycles:

```powershell
.venv\Scripts\python -m hex6.train.run_cycle --config configs/colab_strongest_v2.toml --output-root artifacts/bootstrap_colab_strongest_v2 --minutes 60
```

Cycle promotion now uses a dedicated stronger lane:

- `promotion_games_per_match = 12`
- `promotion_opening_suite = configs/experiments/promotion_opening_suite.toml`
- participants: `candidate`, `incumbent`, and `baseline`

Arena eval:

```powershell
.venv\Scripts\python -m hex6.eval.run_arena --config configs/colab.toml --checkpoint artifacts/bootstrap_fast/bootstrap_model.pt --output artifacts/arena
```

Tournament eval:

```powershell
.venv\Scripts\python -m hex6.eval.run_tournament --config configs/fast.toml --output artifacts/tournament/latest --games-per-match 4 --max-game-plies 0 --opening-suite configs/experiments/opening_suite.toml --max-checkpoints 3 --checkpoint-glob "artifacts/**/bootstrap_model.pt" --include-baseline --include-random
```

Search matrix:

```powershell
.venv\Scripts\python -m hex6.eval.run_search_matrix --matrix configs/experiments/search_matrix.toml --output artifacts/search_matrix
```

Watch Colab status:

```powershell
.venv\Scripts\python -m hex6.integration.watch_status --config configs/colab_hour.toml --run-id latest
```

Colab priority loop:

```powershell
.venv\Scripts\python -m hex6.integration.run_priority_loop --queue configs/colab_job_queue.toml --state artifacts/colab_queue/state.dev.json --once --dry-run
```

Colab helper script:

```powershell
python scripts/colab_run.py cycle --repo-root /content/drive/MyDrive/Hex-A-Toe --config configs/colab_strongest_v2.toml --output-root artifacts/bootstrap_colab_strongest_v2 --minutes 60
```

Colab runtime benchmark:

```powershell
python scripts/colab_run.py runtime-benchmark --repo-root /content/drive/MyDrive/Hex-A-Toe --minimum-gpu-tier V100 --config configs/colab_strongest_v2.toml --output artifacts/runtime_parallelism_colab --cpu-threads 8 --interop-threads 2 --self-play-workers 4 8 12 --data-loader-workers 2 --parallel-expansions-per-root 4 6 8 --root-simulations 96 --bootstrap-games 2 --epochs 1 --max-game-plies 0
```

Colab efficiency queue:

```powershell
.venv\Scripts\python -m hex6.integration.run_priority_loop --queue configs/colab_efficiency_queue.toml --state artifacts/colab_queue/efficiency.state.dev.json --once --dry-run
```

Refresh the executive review:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_executive_review.ps1
```

## Deployment

Local build check:

```powershell
.venv\Scripts\python build.py
```

Production deploy:

```powershell
vercel --prod --yes
```

## Verification

Lint:

```powershell
.venv\Scripts\ruff check .
```

Full test suite:

```powershell
.venv\Scripts\python -m pytest
```

## Optional Research Tooling

Install the repo-local research stack into the project virtualenv:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -e .[dev,research]
```

Included in the `research` extra:

- `wandb`: hosted experiment tracking
- `optuna`: hyperparameter search
- `py-spy`: Python sampling profiler

Already available from the existing repo dependencies:

- `torch.profiler`: bundled with PyTorch

Not part of the repo-local Python extra:

- `NVIDIA Nsight Systems`: system-level NVIDIA profiler
- `OpenSpiel`: reference framework; Windows install requires a native build toolchain such as CMake
- `Aim`: currently not reliable on this Windows/Python environment because its `aimrocks` dependency does not resolve cleanly here

### Optional W&B tracking

W&B tracking is opt-in and controlled entirely by environment variables so normal runs are unaffected.

Tracked local/offline bootstrap example:

```powershell
$env:HEX6_ENABLE_WANDB = "1"
$env:HEX6_WANDB_MODE = "offline"
$env:HEX6_WANDB_PROJECT = "hex6-bot"
$env:WANDB_DIR = "C:\\Hexagonal tic tac toe\\artifacts\\wandb"
.venv\Scripts\python -m hex6.train.run_bootstrap --config configs/fast.toml --output artifacts/bootstrap_fast_tracked
```

Useful variables:

- `HEX6_ENABLE_WANDB=1`
- `HEX6_WANDB_MODE=offline|online|disabled`
- `HEX6_WANDB_PROJECT=<project>`
- `HEX6_WANDB_ENTITY=<entity>`
- `HEX6_WANDB_GROUP=<group>`
- `HEX6_WANDB_TAGS=tag1,tag2`
- `HEX6_WANDB_RUN_NAME=<name>`
- `WANDB_DIR=<artifact dir>`

### py-spy profiling wrapper

Example:

```powershell
.venv\Scripts\python scripts/profile_hex6.py --output artifacts/profiles/fast_bootstrap.speedscope.json --format speedscope -- .venv\Scripts\python -m hex6.train.run_bootstrap --config configs/fast.toml --output artifacts/bootstrap_fast_profiled
```

### Parallelism sweep

Benchmark `self_play_workers` and `parallel_expansions_per_root` together without post-train eval noise:

```powershell
.venv\Scripts\python -m hex6.train.benchmark_runtime --config configs/colab_strongest_v2.toml --output artifacts/runtime_parallelism_sweep --cpu-threads 8 --interop-threads 2 --self-play-workers 4 8 12 --data-loader-workers 0 --parallel-expansions-per-root 1 4 6 8 --root-simulations 96 --bootstrap-games 2 --epochs 1 --max-game-plies 0
```
