# AGENTS.md

Agent operating guide for this repository.

## Goal

Build and iterate on a modular Hex6 bot with:

- Config-first behavior (`configs/*.toml` is the source of truth for tunables).
- Sparse, effectively infinite board rules.
- Clear package boundaries across game/search/nn/train/eval/web/integration.

## Fast Start

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
.venv\Scripts\ruff check .
.venv\Scripts\python -m pytest
```

## Canonical Commands

- Local web app: `.venv\Scripts\python -m hex6.web.run_server --config configs/play.toml --host 127.0.0.1 --port 5000`
- Fast bootstrap: `.venv\Scripts\python -m hex6.train.run_bootstrap --config configs/fast.toml --output artifacts/bootstrap_fast`
- Time-boxed cycles: `.venv\Scripts\python -m hex6.train.run_cycle --config configs/colab_hour.toml --output-root artifacts/bootstrap_colab_hour --minutes 60`
- Arena eval: `.venv\Scripts\python -m hex6.eval.run_arena --config configs/colab.toml --checkpoint <checkpoint.pt> --output artifacts/arena`
- Search matrix: `.venv\Scripts\python -m hex6.eval.run_search_matrix --matrix configs/experiments/search_matrix.toml --output artifacts/search_matrix`

## Source Of Truth Files

- Global schema: `src/hex6/config/schema.py`
- Runtime profiles: `configs/default.toml`, `configs/fast.toml`, `configs/colab.toml`, `configs/colab_hour.toml`, `configs/play.toml`
- Web API: `src/hex6/web/app.py`
- Game rules/state transitions: `src/hex6/game/state.py`
- Baseline search behavior: `src/hex6/search/baseline.py`
- Bootstrap/cycle training loop: `src/hex6/train/bootstrap.py`, `src/hex6/train/run_cycle.py`
- Status bridge contracts: `src/hex6/integration/status.py`

## Hard Invariants

1. The rules layer accepts legal placements on an effectively infinite board. Do not add hidden board bounds in `GameState`.
2. Turn semantics are strict: opening uses `opening_placements`; later turns use `turn_placements`.
3. A winning placement ends the game immediately, even mid-turn.
4. Keep gameplay/search/training assumptions in config where practical instead of hard-coded constants.
5. If config schema changes, all runtime profiles and impacted tests must be updated in the same change.
6. Web payloads are anchor-relative in play mode; keep API response shape stable unless intentionally versioned.

## Verification Matrix

- `src/hex6/game/**` -> `tests/test_game_state.py` and related search tests.
- `src/hex6/search/**` -> `tests/test_search_baseline.py`, `tests/test_candidate_explorer.py`, arena/search-matrix tests.
- `src/hex6/web/**` -> `tests/test_web_app.py`.
- `src/hex6/config/**` or `configs/**` -> `tests/test_config_loader.py`, `tests/test_config_variants.py`.
- `src/hex6/train/**` or `src/hex6/eval/**` -> targeted eval tests plus at least one end-to-end CLI smoke command.
- Cross-cutting edits -> run full suite: `.venv\Scripts\python -m pytest`.

## Safe Change Pattern

1. Read the closest module + its tests before editing.
2. Prefer the smallest change that preserves current contracts.
3. Add/update tests with behavior changes.
4. Run the narrowest relevant tests first, then broader checks.
5. Keep doc updates in the same change when behavior or commands change.

## Artifacts And Secrets

- Do not commit generated artifacts under `artifacts/`.
- Do not hardcode tokens. `HEX6_GITHUB_TOKEN` / `GITHUB_TOKEN` are resolved at runtime for GitHub status transport.
- Treat `status_backend=github_branch` as a networked mode; keep tests deterministic by using `none` or `file` backends.
