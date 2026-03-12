# Hex6 Bot

Hex6 Bot is a config-first research repository for a sparse-board hexagonal connection game and its training stack.
The current default lane is a bounded `15 x 15` board, AlphaZero-style self-play, and a web surface for local play
and engine-backed demos.

## Quick Start

Python `3.11` is the intended local version.

If you want CUDA, install the appropriate PyTorch wheel first from the official PyTorch selector. A plain
`pip install -e .[dev]` will otherwise install the default wheel for your platform. The current workflow is
local-first again: use the local machine for development, training, evaluation, and profiling. Colab tooling
remains in the repo as an optional remote path, not the default.

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
.venv\Scripts\ruff check .
.venv\Scripts\python -m pytest
```

## Repository Map

Top-level entrypoints:

- `app.py`: Vercel/hosted web entrypoint.
- `AGENTS.md`: repo contract and AI-oriented guardrails.
- `CONTRIBUTING.md`: contributor workflow and PR expectations.
- `configs/`: runtime profiles and experiment matrices.
- `docs/`: architecture, workflow, and experiment notes.
- `scripts/`: utility PowerShell scripts for report generation and maintenance.
- `src/hex6/`: application package.
- `tests/`: unit and integration coverage.

Package map:

- `src/hex6/config`: typed schema, config loading, and profile helpers.
- `src/hex6/game`: axial coordinates, sparse state transitions, and win/draw rules.
- `src/hex6/search`: baseline search, guided MCTS, model-guided search, and heuristics.
- `src/hex6/nn`: PyTorch encoder/model code.
- `src/hex6/train`: bootstrap and repeated self-play training loops.
- `src/hex6/eval`: arena, tournament, opening-suite, and search-matrix evaluation.
- `src/hex6/web`: Flask app, templates, and frontend assets.
- `src/hex6/integration`: status transport and priority-loop integration.
- `src/hex6/prototype`: importable experimental logic that has not fully graduated.

## Config Profiles

Current supported profiles:

- `configs/default.toml`: shared default research lane.
- `configs/fast.toml`: fastest local training profile.
- `configs/play.toml`: website/play profile.
- `configs/local_4h_strongest_v2.toml`: strongest stable local cycle lane.
- `configs/local_4h_strongest_v2_gumbel.toml`: strongest experimental local cycle lane.

Historical or comparison profiles are still present for reproducibility, but they are no longer the main surface to optimize against. See `configs/README.md` for the current vs historical split.

## Common Commands

Website:

```powershell
.venv\Scripts\python -m hex6.web.run_server --config configs/play.toml --host 127.0.0.1 --port 5000
```

Fast bootstrap smoke:

```powershell
.venv\Scripts\python -m hex6.train.run_bootstrap --config configs/fast.toml --output artifacts/bootstrap_fast
```

Repeated cycle:

```powershell
.venv\Scripts\python -m hex6.train.run_cycle --config configs/local_4h_strongest_v2.toml --output-root artifacts/alphazero_cycle_local_strongest_v2 --minutes 60 --status-backend none
```

Experimental strongest lane:

```powershell
.venv\Scripts\python -m hex6.train.run_cycle --config configs/local_4h_strongest_v2_gumbel.toml --output-root artifacts/alphazero_cycle_local_strongest_v2_gumbel --minutes 60 --status-backend none
```

Arena eval:

```powershell
.venv\Scripts\python -m hex6.eval.run_arena --config configs/colab.toml --checkpoint <checkpoint.pt> --output artifacts/arena
```

Tournament eval:

```powershell
.venv\Scripts\python -m hex6.eval.run_tournament --config configs/fast.toml --output artifacts/tournament/latest --games-per-match 4 --max-game-plies 0 --opening-suite configs/experiments/conversion_opening_suite.toml --max-checkpoints 3 --checkpoint-glob "artifacts/**/bootstrap_model.pt" --include-baseline --include-random
```

Search matrix:

```powershell
.venv\Scripts\python -m hex6.eval.run_search_matrix --matrix configs/experiments/search_matrix.toml --output artifacts/search_matrix
```

## Documentation Index

Start here:

- `docs/index.md`: repo navigation guide and document map.
- `docs/current-state.md`: supported profiles, workflow, and current priorities.
- `docs/architecture.md`: high-level package structure.
- `docs/tools.md`: canonical commands.
- `docs/ai-agent-workflows.md`: task-specific edit/test workflows.

Operational docs:

- `docs/vercel.md`: deploy notes.
- `docs/open-source-checklist.md`

Current research docs:

- `docs/literature-improvements.md`
- `docs/literature-roadmap.md`
- `docs/performance-roadmap.md`
- `docs/game-exploration.md`

Historical reports and old workflow notes:

- `docs/archive.md`

## Change Safety

- Keep game/search/training assumptions in config when practical.
- Update tests in the same change when behavior changes.
- If the config schema changes, update affected profiles and tests together.
- Do not commit generated artifacts under `artifacts/`.

`AGENTS.md` is the authoritative repo contract for AI agents. `CONTRIBUTING.md` is the human-facing version.

## Publishing Notes

The repo is structurally ready for GitHub upload, but open-source publication still needs project-owner decisions:

- choose a license and add `LICENSE`
- set final repository URLs in `pyproject.toml`
- decide whether to add `SECURITY.md` and a code of conduct

Those remaining manual items are tracked in `docs/open-source-checklist.md`.
