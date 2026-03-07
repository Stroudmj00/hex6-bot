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
