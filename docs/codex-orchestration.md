# Codex Orchestration Setup

This repo now includes a project-local Codex config at `.codex/config.toml`.
Global defaults were also applied at `C:\Users\Admin\.codex\config.toml`.

## What Is Configured

- Main/orchestrator model: `gpt-5.4`
- Sub-agent model: `gpt-5.3-codex-spark`
- Multi-agent feature enabled.
- Default mode is YOLO autonomy:
  - `approval_policy = "never"`
  - `sandbox_mode = "danger-full-access"`
  - `web_search = "live"`
- Specialized agent roles:
  - `explorer` (read-only analysis)
  - `worker` (implementation + tests)
  - `reviewer` (risk/regression review)
  - `monitor` (long-running command status)
- Two profiles:
  - `safe`: asks approvals when needed
  - `yolo`: danger-full-access + live web search

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

## One-Hour Check-In Automation

- Baseline file: `artifacts/checkins/baseline.json`
- Report script: `scripts/one_hour_checkin.ps1`
- Wrapper script (runs report + updates baseline + refreshes review): `scripts/hourly_checkin.ps1`
- Output reports: `artifacts/checkins/checkin-*.md`

## Recurring Automation

Set up recurring automation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup_automation_tasks.ps1
```

What this configures:

- Removes the legacy local heavy-compute automation hooks.
- Installs Startup launchers for:
  - `scripts/start_colab_status_watch.ps1`
  - `scripts/start_local_web_app.ps1`
- Starts the status watcher and local website immediately.
- Leaves recurring heavy training/eval work to Colab.
- Background process logs are written under `artifacts/local_ops/`.

For recurring Colab heavy jobs with explicit priority scores, run:

```powershell
.venv\Scripts\python -m hex6.integration.run_priority_loop --queue configs/colab_job_queue.toml --state artifacts/colab_queue/state.json --status-backend github_branch
```

Or in Colab notebook, set:

- `RUN_MODE = "priority_loop"`

Key scripts:

- `scripts/stop_local_heavy_jobs.ps1`
- `scripts/start_colab_status_watch.ps1`
- `scripts/start_local_web_app.ps1`
- `scripts/start_yolo_autopilot.ps1`

## Kick Off YOLO Autopilot

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_yolo_autopilot.ps1 -DurationMinutes 60 -Profile yolo
```

That command still uses local compute and is now intended to be a manual,
one-off action rather than the recurring default.

Check status:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/autopilot_status.ps1
```

Executive review output remains available at `docs/executive-review.md` when you
run the reporting scripts manually.

## Notes For VS Code Extension

- Use Agent mode for implementation tasks.
- Use cloud delegation for long/heavy tasks when available in your extension build.
- Multi-agent orchestration is also available in Codex CLI; use CLI if you want explicit parallel sub-agent workflows.
