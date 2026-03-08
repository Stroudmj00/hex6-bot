# Tooling Guide

## Core local commands

### Website

```powershell
.venv\Scripts\python -m hex6.web.run_server --config configs/play.toml --host 127.0.0.1 --port 5000
```

### One-shot bootstrap training

```powershell
.venv\Scripts\python -m hex6.train.run_bootstrap --config configs/fast.toml --output artifacts/bootstrap_fast
```

### Repeated training/eval cycles

```powershell
.venv\Scripts\python -m hex6.train.run_cycle --config configs/colab_hour.toml --output-root artifacts/bootstrap_colab_hour --minutes 60
```

### Watch Colab status

```powershell
.venv\Scripts\python -m hex6.integration.watch_status --config configs/colab_hour.toml --run-id latest
```

### Checkpoint vs baseline arena

```powershell
.venv\Scripts\python -m hex6.eval.run_arena --config configs/colab.toml --checkpoint artifacts/bootstrap_fast/bootstrap_model.pt --output artifacts/arena
```

Use a stable output folder (for example `artifacts/arena_history`) if you want one
continuous `elo_history.json` file for that lane of experiments.

### Checkpoint vs random arena

```powershell
.venv\Scripts\python -m hex6.eval.run_arena --config configs/fast.toml --checkpoint artifacts/bootstrap_fast/bootstrap_model.pt --opponent random --random-seed 7 --output artifacts/arena_random
```

### Round-robin tournament (baseline + random + latest checkpoints)

```powershell
.venv\Scripts\python -m hex6.eval.run_tournament --config configs/fast.toml --output artifacts/tournament/latest --games-per-match 2 --max-game-plies 48 --max-checkpoints 3 --checkpoint-glob "artifacts/**/bootstrap_model.pt" --include-baseline --include-random
```

### Search variant matrix

```powershell
.venv\Scripts\python -m hex6.eval.run_search_matrix --matrix configs/experiments/search_matrix.toml --output artifacts/search_matrix
```

## Deployment

### Local Vercel build check

```powershell
.venv\Scripts\python build.py
```

### Production deploy

```powershell
vercel --prod --yes
```

## Verification

### Lint

```powershell
.venv\Scripts\ruff check .
```

### Test suite

```powershell
.venv\Scripts\python -m pytest
```

## Lightweight Local Automation

### Configure watch-only startup launchers

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup_automation_tasks.ps1
```

This disables the recurring heavy local jobs and installs Startup launchers for:
- `scripts/start_colab_status_watch.ps1`
- `scripts/start_local_web_app.ps1`
The launched background process logs are written under `artifacts/local_ops/`.

### Stop legacy heavy local jobs now

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/stop_local_heavy_jobs.ps1
```

### Start one local status watcher now

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_colab_status_watch.ps1
```

This starts the watcher in the background and returns immediately.

### Start the local web app now

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_local_web_app.ps1
```

This starts the server in the background and returns immediately.

## Manual Local Compute

### Start one YOLO run now

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_yolo_autopilot.ps1 -DurationMinutes 60 -Profile yolo
```

### Show autopilot status

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/autopilot_status.ps1
```

### Run hourly check-in immediately

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/hourly_checkin.ps1
```

### Run competitive eval immediately

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_competitive_eval.ps1
```

### Refresh executive review now (includes merged Elo trend over time)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_executive_review.ps1
```

## Colab-Offloaded Eval Commands

### Search variant matrix with status publishing

```powershell
.venv\Scripts\python -m hex6.eval.run_search_matrix --matrix configs/experiments/search_matrix.toml --output artifacts/search_matrix_colab --run-id colab-search-matrix --status-backend github_branch
```

### Round-robin tournament with status publishing

```powershell
.venv\Scripts\python -m hex6.eval.run_tournament --config configs/fast.toml --output artifacts/tournament/colab_latest --games-per-match 2 --max-game-plies 48 --max-checkpoints 3 --checkpoint-glob "artifacts/**/bootstrap_model.pt" --include-baseline --include-random --run-id colab-tournament --status-backend github_branch
```

### Priority-scored Colab GPU loop (recommended for always-on queueing)

```powershell
.venv\Scripts\python -m hex6.integration.run_priority_loop --queue configs/colab_job_queue.toml --state artifacts/colab_queue/state.json --status-backend github_branch
```

The default queue includes explicit `priority` scores and runs tournament eval at
`max_game_plies = 100` to reduce draw-cap artifacts.
