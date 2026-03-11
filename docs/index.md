# Documentation Index

This file is the stable starting point for new contributors and AI agents.

## Read Order

1. `README.md`
2. `AGENTS.md`
3. `CONTRIBUTING.md`
4. `docs/architecture.md`
5. `docs/tools.md`

After that, pick the closest task-specific document below.

## Repository Navigation

Core package map:

- `src/hex6/config`: schema and config loading.
- `src/hex6/game`: board rules, turn semantics, and terminal checks.
- `src/hex6/search`: baseline search, guided MCTS, and heuristics.
- `src/hex6/nn`: encoder/model code.
- `src/hex6/train`: bootstrap and repeated training loops.
- `src/hex6/eval`: arena, tournament, and search-matrix evaluation.
- `src/hex6/web`: Flask app and website frontend.
- `src/hex6/integration`: status bridge and job orchestration helpers.
- `src/hex6/prototype`: experimental logic that remains importable.

Top-level files:

- `app.py`: hosted web entrypoint.
- `pyproject.toml`: package metadata, dependencies, Ruff, and pytest config.
- `configs/`: runtime profiles and experiment suites.
- `tests/`: verification matrix.

## Config Profile Matrix

- `configs/default.toml`: base default lane.
- `configs/fast.toml`: fastest local training loop.
- `configs/colab.toml`: medium Colab run.
- `configs/colab_hour.toml`: repeated cycle lane.
- `configs/colab_strongest_v2.toml`: strongest current Colab cycle lane.
- `configs/play.toml`: website profile.
- `configs/colab_job_queue.toml`: priority-loop job definitions.
- `configs/experiments/search_matrix.toml`: search sweep matrix.
- `configs/experiments/*opening_suite*.toml`: fixed opening suites for training, eval, and promotion.

## Workflow Docs

- `docs/ai-agent-workflows.md`: task recipes by subsystem.
- `docs/tools.md`: canonical commands and local-vs-Colab split.
- `docs/colab.md`: remote-first training workflow.
- `docs/vscode-colab-extension.md`: quickest VS Code extension path into Colab.
- `docs/vercel.md`: deploy workflow.
- `docs/codex-orchestration.md`: AI-assisted workflow notes.

## Architecture And Research Docs

- `docs/architecture.md`: design principles and package outline.
- `docs/game-exploration.md`: game/rules notes.
- `docs/model-journey.md`: checkpoint progression.
- `docs/literature-improvements.md`: literature-backed changes.
- `docs/literature-roadmap.md`: cross-paradigm roadmap for the strongest engine.
- `docs/performance-roadmap.md`: measured bottlenecks and likely next performance refactors.
- `docs/next-experiment-options.md`: next tuning ideas.
- `docs/executive-review.md`: current high-level status.

## Historical / Report Docs

These are useful context, but not the first files to read when making product or engine changes:

- `docs/alphazero-20-cycle-report.md`
- `docs/alphazero-cycle-story.md`
- `docs/board-size-ablation.md`
- `docs/lit-vs-prelit-20m.md`
- `docs/project-memory.md`

## Open-Source Release Notes

See `docs/open-source-checklist.md` for the small set of project-owner decisions that still need to be made before public release.
