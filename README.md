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
- `docs/game-exploration.md`: working notes about the game and the search problem.
- `docs/architecture.md`: package boundaries and intended module responsibilities.
- `docs/roadmap.md`: staged implementation plan.
- `docs/5-hour-sprint.md`: time-boxed execution plan with feedback checkpoints.
- `docs/colab.md`: Colab setup and training flow.
- `src/hex6/prototype/candidate_explorer.py`: importable exploration module.

## Fast bootstrap run

```powershell
.venv\Scripts\python -m hex6.train.run_bootstrap --config configs/fast.toml --output artifacts/bootstrap_fast
```
