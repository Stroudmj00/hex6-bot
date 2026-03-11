# AI Agent Workflows

This playbook is for Codex/AI agents making code changes in this repo.

Read `AGENTS.md` first, then `docs/index.md`, then use the task recipe below.

## Workflow 1: Game Rules Change

Use for turn-order, legality, winner detection, or coordinate behavior updates.

1. Edit `src/hex6/game/state.py` (and `src/hex6/game/axial.py` or `symmetry.py` only if required).
2. Validate related assumptions in `configs/*.toml` and `src/hex6/config/schema.py`.
3. Update/add tests in `tests/test_game_state.py`.
4. Run:
   - `.venv\Scripts\python -m pytest tests/test_game_state.py`
   - `.venv\Scripts\python -m pytest tests/test_search_baseline.py`

## Workflow 2: Search Or Heuristic Tuning

Use for candidate generation, baseline turn ranking, or heuristic scoring changes.

1. Edit `src/hex6/search/baseline.py`, `src/hex6/search/heuristics.py`, or `src/hex6/prototype/candidate_explorer.py`.
2. Keep scoring knobs in config when practical (`[scoring]`, `[heuristic]`, `[prototype]`, `[search]` sections).
3. Update/add tests:
   - `tests/test_search_baseline.py`
   - `tests/test_candidate_explorer.py`
4. Run:
   - `.venv\Scripts\python -m pytest tests/test_search_baseline.py tests/test_candidate_explorer.py`
   - Optional smoke: `.venv\Scripts\python -m hex6.eval.run_search_matrix --matrix configs/experiments/search_matrix.toml --output artifacts/search_matrix`

## Workflow 3: Config Schema/Profile Change

Use for adding new knobs, changing default values, or profile behavior.

1. Edit `src/hex6/config/schema.py` and any helper loaders/override utilities.
2. Update all relevant config profiles under `configs/`.
3. Update docs/commands if behavior changes.
4. Update/add tests:
   - `tests/test_config_loader.py`
   - `tests/test_config_variants.py`
5. Run:
   - `.venv\Scripts\python -m pytest tests/test_config_loader.py tests/test_config_variants.py`

## Workflow 4: Web/UI Or API Change

Use for HTTP endpoints, session payload shape, or browser behavior.

1. Backend edits:
   - `src/hex6/web/app.py`
   - `src/hex6/web/run_server.py`
2. Frontend edits:
   - `src/hex6/web/templates/index.html`
   - `src/hex6/web/static/app.js`
   - `src/hex6/web/static/local_game.js`
   - `src/hex6/web/static/rule_demos.js`
   - `src/hex6/web/static/styles.css`
3. Keep response structure stable unless intentionally changing API contract.
4. Update/add `tests/test_web_app.py`.
5. Run:
   - `.venv\Scripts\python -m pytest tests/test_web_app.py`
   - Manual smoke: launch server and play 1 short game.

## Workflow 5: Training/Evaluation Loop Change

Use for bootstrap generation, loop scheduling, or checkpoint evaluation behavior.

1. Edit:
   - `src/hex6/train/bootstrap.py`
   - `src/hex6/train/run_bootstrap.py`
   - `src/hex6/train/run_cycle.py`
   - `src/hex6/eval/*.py` as needed
2. Keep long-running commands optional and config-driven.
3. Default policy:
   - local only for smoke/debug jobs expected to finish in 20 minutes or less
   - Colab for longer training/eval runs
4. Update/add tests:
   - `tests/test_arena.py`
   - `tests/test_opening_suite.py`
5. Run:
   - `.venv\Scripts\python -m pytest tests/test_arena.py tests/test_opening_suite.py`
   - Optional smoke: `.venv\Scripts\python -m hex6.train.run_bootstrap --config configs/fast.toml --output artifacts/bootstrap_fast`

## Workflow 6: Colab Priority Queue Change

Use for always-on Colab GPU scheduling, queue priorities, or job selection policy.

1. Edit:
   - `configs/colab_job_queue.toml`
   - `src/hex6/integration/run_priority_loop.py`
   - `docs/colab.md` and `docs/tools.md` if command flow changes
2. Keep job definitions explicit:
   - `id`, `kind`, `priority`, `min_interval_minutes`
   - optional fairness cap: `max_consecutive_runs`
3. Update/add tests:
   - `tests/test_priority_loop.py`
4. Run:
   - `.venv\Scripts\ruff check src/hex6/integration/run_priority_loop.py tests/test_priority_loop.py`
   - `.venv\Scripts\python -m pytest tests/test_priority_loop.py`
   - Optional dry-run: `.venv\Scripts\python -m hex6.integration.run_priority_loop --queue configs/colab_job_queue.toml --state artifacts/colab_queue/state.dev.json --once --dry-run`

## Final Pre-PR Check

Run before finishing cross-cutting edits:

```powershell
.venv\Scripts\ruff check .
.venv\Scripts\python -m pytest
```

If any command is skipped, state exactly what was skipped and why.
