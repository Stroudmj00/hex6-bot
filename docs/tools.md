# Tooling Guide

## Core local commands

Use the local machine for development, training, evaluation, and profiling.
Historical Colab tooling remains in the repo for reproducibility only; it is not part of the primary workflow.

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
.venv\Scripts\python -m hex6.train.run_cycle --config configs/local_4h_strongest_v2.toml --output-root artifacts/alphazero_cycle_local_strongest_v2 --minutes 60 --status-backend none
```

Experimental strongest cycle:

```powershell
.venv\Scripts\python -m hex6.train.run_cycle --config configs/local_4h_strongest_v2_gumbel.toml --output-root artifacts/alphazero_cycle_local_strongest_v2_gumbel --minutes 60 --status-backend none
```

Cycle promotion now uses a dedicated stronger lane:

- `promotion_games_per_match = 12`
- `promotion_opening_suite = configs/experiments/promotion_opening_suite.toml`
- participants: `candidate`, `incumbent`, and `baseline`

Arena eval:

```powershell
.venv\Scripts\python -m hex6.eval.run_arena --config configs/local_4h_strongest_v2.toml --checkpoint artifacts/alphazero_cycle_4h_strongest_v2/cycle_002/bootstrap_model.pt --output artifacts/arena
```

Tournament eval:

```powershell
.venv\Scripts\python -m hex6.eval.run_tournament --config configs/fast.toml --output artifacts/tournament/latest --games-per-match 4 --max-game-plies 0 --opening-suite configs/experiments/opening_suite.toml --max-checkpoints 3 --checkpoint-glob "artifacts/**/bootstrap_model.pt" --include-baseline --include-random
```

Search matrix:

```powershell
.venv\Scripts\python -m hex6.eval.run_search_matrix --matrix configs/experiments/search_matrix.toml --output artifacts/search_matrix
```

Local runtime benchmark:

```powershell
.venv\Scripts\python -m hex6.train.benchmark_runtime --config configs/local_4h_strongest_v2.toml --output artifacts/runtime_parallelism_local --cpu-threads 8 --interop-threads 2 --self-play-workers 4 8 12 --data-loader-workers 0 --parallel-expansions-per-root 4 6 8 --root-simulations 96 --bootstrap-games 2 --epochs 1 --max-game-plies 0
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
.venv\Scripts\python -m hex6.train.benchmark_runtime --config configs/local_4h_strongest_v2.toml --output artifacts/runtime_parallelism_sweep --cpu-threads 8 --interop-threads 2 --self-play-workers 4 8 12 --data-loader-workers 0 --parallel-expansions-per-root 1 4 6 8 --root-simulations 96 --bootstrap-games 2 --epochs 1 --max-game-plies 0
```

## Historical / Deprecated Workflow Notes

- `docs/colab.md`
- `docs/vscode-colab-extension.md`
- `docs/archive.md`

These remain in the repo so older experiment notes and automation references still resolve, but they are not the primary workflow surface anymore.
