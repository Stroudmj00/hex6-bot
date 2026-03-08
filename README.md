# Hex6 Bot

Research scaffold for a modular bot for the hexagonal `6 in a row` variant discussed in
the `can tic-tac-toe, with hexagons?` video.

## Current goals

- Keep all key game/search/model assumptions in configuration files.
- Treat the board as sparse and effectively infinite.
- Explore candidate generation with live cells, dead zones, and long-range "island" ideas.
- Keep the codebase modular, importable, and easy to expand later.

## Local environment

The repository is set up for a dedicated Python `3.11` virtual environment:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
```

`3.11` is intentional because the current machine also has `3.14`, which is a poor default
for GPU ML packages.

## AI agent quickstart

- Agent contract and invariants: `AGENTS.md`
- Task-specific edit/test recipes: `docs/ai-agent-workflows.md`
- Multi-agent orchestration setup: `docs/codex-orchestration.md`
- Executive status snapshot (including Elo-over-time trend): `docs/executive-review.md`
- Canonical command reference: `docs/tools.md`

Recommended pre-change check:

```powershell
.venv\Scripts\ruff check .
.venv\Scripts\python -m pytest
```

Lightweight local background setup (Colab watch + local web app):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup_automation_tasks.ps1
```

This removes the legacy heavy local automation and installs Startup launchers
for `watch_status` plus the local website. Heavy training/eval is intended to
run in Colab.

## Repository map

- `configs/default.toml`: game, search, training, and prototype assumptions.
- `configs/fast.toml`: reduced profile for fast local/Colab iteration.
- `configs/colab.toml`: medium-scale Colab training profile.
- `configs/colab_hour.toml`: longer Colab cycle profile with post-cycle Elo tracking.
- `configs/play.toml`: local website/play profile.
- `docs/game-exploration.md`: working notes about the game and the search problem.
- `docs/architecture.md`: package boundaries and intended module responsibilities.
- `docs/roadmap.md`: staged implementation plan.
- `docs/5-hour-sprint.md`: time-boxed execution plan with feedback checkpoints.
- `docs/colab.md`: Colab setup and training flow.
- `docs/tools.md`: command reference for training, evaluation, deployment, and local play.
- `docs/experiment-report.md`: current interpretation of arena and search-matrix results.
- `docs/vercel.md`: Vercel deployment notes for the website.
- `docs/project-memory.md`: persistent project assumptions and operating constraints.
- `src/hex6/integration/`: explicit status bridge between Colab and local tooling.
- `src/hex6/web/`: local website and API for human-vs-bot play.
- `src/hex6/prototype/candidate_explorer.py`: importable exploration module.

## Fast bootstrap run

```powershell
.venv\Scripts\python -m hex6.train.run_bootstrap --config configs/fast.toml --output artifacts/bootstrap_fast
```

## Colab bootstrap run

```powershell
.venv\Scripts\python -m hex6.train.run_bootstrap --config configs/colab.toml --output artifacts/bootstrap_colab
```

## Colab hour-cycle run

```powershell
.venv\Scripts\python -m hex6.train.run_cycle --config configs/colab_hour.toml --output-root artifacts/bootstrap_colab_hour --minutes 60
```

## Colab priority queue loop

```powershell
.venv\Scripts\python -m hex6.integration.run_priority_loop --queue configs/colab_job_queue.toml --state artifacts/colab_queue/state.json --status-backend github_branch
```

The Colab notebook prints repo freshness metadata (`head_short`, commit
timestamps, latest-`origin/main` check) and writes the same data to
`repo_version.json` in the output folder for each run.

## Colab search-matrix run

```powershell
.venv\Scripts\python -m hex6.eval.run_search_matrix --matrix configs/experiments/search_matrix.toml --output artifacts/search_matrix_colab --run-id colab-search-matrix --status-backend github_branch
```

## Colab tournament run

```powershell
.venv\Scripts\python -m hex6.eval.run_tournament --config configs/fast.toml --output artifacts/tournament/colab_latest --games-per-match 4 --max-game-plies 120 --opening-suite configs/experiments/opening_suite.toml --max-checkpoints 3 --checkpoint-glob "artifacts/**/bootstrap_model.pt" --include-baseline --include-random --run-id colab-tournament --status-backend github_branch
```

## Competitive tournament eval

```powershell
.venv\Scripts\python -m hex6.eval.run_tournament --config configs/fast.toml --output artifacts/tournament/latest --games-per-match 4 --max-game-plies 120 --opening-suite configs/experiments/opening_suite.toml --max-checkpoints 3 --checkpoint-glob "artifacts/**/bootstrap_model.pt" --include-baseline --include-random
```

## Benchmark local runtime

```powershell
.venv\Scripts\python -m hex6.train.benchmark_runtime --config configs/default.toml --output artifacts/runtime_benchmark
```

Current best-known local training setting on this machine is:
- `runtime.cpu_threads = 12`
- `runtime.interop_threads = 2`
- `training.self_play_workers = 4`
- `training.data_loader_workers = 0`

## Watch Colab status

```powershell
.venv\Scripts\python -m hex6.integration.watch_status --config configs/colab.toml --run-id latest
```

## Local website

```powershell
.venv\Scripts\python -m hex6.web.run_server --config configs/play.toml --host 127.0.0.1 --port 5000
```

## Vercel website

The repo includes a root `app.py` and build step for Vercel. See
`docs/vercel.md`.
