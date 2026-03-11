# Contributing

This repository is still evolving quickly, so small, well-scoped changes are preferred over large mixed refactors.

## First Read

1. `README.md`
2. `AGENTS.md`
3. `docs/index.md`
4. the nearest module and its tests

## Local Setup

Python `3.11` is the intended local version.

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
```

If you want CUDA support, install the appropriate PyTorch wheel first from the official PyTorch selector.

## Required Checks

Run the narrowest relevant checks first, then broaden if the change crosses subsystem boundaries.

Typical checks:

- `.\.venv\Scripts\ruff check .`
- `.\.venv\Scripts\python -m pytest`

Targeted examples:

- Game rules: `.\.venv\Scripts\python -m pytest tests/test_game_state.py tests/test_search_baseline.py`
- Search: `.\.venv\Scripts\python -m pytest tests/test_search_baseline.py tests/test_candidate_explorer.py`
- Config/schema: `.\.venv\Scripts\python -m pytest tests/test_config_loader.py tests/test_config_variants.py`
- Web: `.\.venv\Scripts\python -m pytest tests/test_web_app.py`

## Change Rules

- Keep gameplay/search/training assumptions in config when practical.
- If `src/hex6/config/schema.py` changes, update affected profiles under `configs/` in the same change.
- If behavior changes, update tests in the same change.
- Keep API response shapes stable unless intentionally changing the contract.
- Do not commit generated outputs under `artifacts/`.
- Do not hardcode secrets or tokens.

## Pull Request Expectations

- Keep each PR focused on one subsystem or one coherent user-facing change.
- Describe the behavior change, not just the files touched.
- List the exact checks you ran.
- If any expected verification was skipped, say what was skipped and why.
- Update docs when commands, workflows, or config semantics change.

## AI Contributors

`AGENTS.md` is the repo contract for AI agents. `docs/ai-agent-workflows.md` contains task-specific edit/test recipes.
