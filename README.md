# Hex6 Bot

Hex6 Bot is a config-first research repository for a sparse-board hexagonal connection game and its training stack.
The current default lane is a bounded `15 x 15` board, AlphaZero-style self-play, and a web surface for local play
and engine-backed demos.

## Quick Start

Python `3.11` is the intended local version.

If you want CUDA, install the appropriate PyTorch wheel first from the official PyTorch selector. A plain
`pip install -e .[dev]` will otherwise install the default wheel for your platform. This repo now treats
the local machine as a development box only: use it for tests, website work, and CPU-only debugging, and
run all real training/evaluation/efficiency experiments on Colab.

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

Stable runtime profiles:

- `configs/default.toml`: shared default research lane.
- `configs/fast.toml`: fastest local training profile.
- `configs/colab.toml`: medium Colab profile.
- `configs/colab_hour.toml`: repeated cycle profile.
- `configs/colab_strongest_v2.toml`: strongest current Colab training lane.
- `configs/play.toml`: website/play profile.

Experiment and evaluation configs:

- `configs/experiments/search_matrix.toml`: search tuning sweeps.
- `configs/experiments/*opening_suite*.toml`: fixed opening suites for training/eval/promotion.
- `configs/fast_19.toml`, `configs/fast_25.toml`, `configs/local_16h_best.toml`: narrower comparison or long-run configs.

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
.venv\Scripts\python -m hex6.train.run_cycle --config configs/colab_strongest_v2.toml --output-root artifacts/bootstrap_colab_strongest_v2 --minutes 60
```

Preferred Colab cycle launch:

```bash
python scripts/colab_run.py cycle --repo-root /content/drive/MyDrive/Hex-A-Toe --minimum-gpu-tier V100 --config configs/colab_strongest_v2.toml --output-root artifacts/bootstrap_colab_strongest_v2 --minutes 60
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
- `docs/architecture.md`: high-level package structure.
- `docs/tools.md`: canonical commands.
- `docs/ai-agent-workflows.md`: task-specific edit/test workflows.

Operational docs:

- `docs/colab.md`: Colab usage and remote workflow.
- `docs/vercel.md`: deploy notes.
- `docs/codex-orchestration.md`: orchestration notes for AI-assisted work.

Research and status docs:

- `docs/executive-review.md`
- `docs/model-journey.md`
- `docs/literature-improvements.md`
- `docs/literature-roadmap.md`
- `docs/next-experiment-options.md`
- `docs/open-source-checklist.md`

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
