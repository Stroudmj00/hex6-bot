# Codex Orchestration Setup

This repo includes a project-local Codex config at `.codex/config.toml`.

## What Is Configured

- main/orchestrator model
- sub-agent model
- multi-agent support
- local validation with `ruff` and `pytest`

## Suggested Workflow

Use one orchestrator prompt that delegates:

```text
@explorer Map the relevant code paths for <goal> and list options with risks.
@worker Implement the best option with minimal diffs and update/add tests.
@reviewer Review the resulting diff for regressions and missing tests.
@monitor Run the final validation commands and summarize pass/fail.
```

## Validation Commands

```powershell
.venv\Scripts\ruff check .
.venv\Scripts\python -m pytest
```

## Notes

- The repo no longer keeps local autopilot/check-in wrapper scripts.
- Use the Python entrypoints in `README.md` and `docs/tools.md` directly.
