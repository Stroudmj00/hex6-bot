# Colab Setup

## Goal

Run the same bootstrap flow in Google Colab so training can use a hosted GPU while the
codebase stays local-friendly.

## Integration boundary

This project should assume:

- Colab is a separate runtime,
- local Codex work cannot directly inspect or control a live Colab session,
- synchronization must happen through explicit artifacts, repository commits, or Drive files.

The current bridge is:

- stdout logs in the notebook,
- `progress.json` written into the output artifact folder,
- `metrics.json` and model checkpoints saved to disk,
- `status/latest.json` plus per-run status files on the `colab-status` branch,
- optional copy-back into Google Drive.

If tighter integration is needed later, build it as an explicit file-based or API-based
bridge rather than assuming hidden shared session access.

## What is ready

- Config-selectable bootstrap CLI.
- Fast profile at `configs/fast.toml`.
- Medium profile at `configs/colab.toml`.
- Hour-cycle profile at `configs/colab_hour.toml`.
- Colab notebook at `notebooks/hex6_colab_fast_bootstrap.ipynb`.
- Notebook modes for bootstrap, cycle, search-matrix, tournament, and priority-loop jobs.
- Local watcher at `python -m hex6.integration.watch_status`.

## One-time GitHub status setup

For the notebook to publish run status back into the repository, add a fine-grained GitHub
token to Colab secrets:

1. Create a fine-grained token with `Contents: Read and write` access to
   `Stroudmj00/hex6-bot`.
2. In Colab, open the secrets panel.
3. Add a secret named `HEX6_GITHUB_TOKEN`.

The token is not stored in this repository. The notebook loads it from Colab secrets at
runtime.

If the secret is absent, the notebook still runs training but disables GitHub status
publishing for that run.

## Recommended first run

Use the fast profile first if you are only checking wiring. For a real sprint run, use
`configs/colab.toml`. For a longer session that should keep producing checkpoints and Elo
history over time, use `configs/colab_hour.toml` with the cycle runner.

The Colab profile is still intentionally conservative:

- no long-range islands,
- narrow candidate counts,
- shallow reply width,
- modest model,
- short bootstrap games,
- a few epochs.

This is not full AlphaZero-style self-training yet. The current longer loop is:

- search-generated self-play data,
- warm-start the next cycle from the previous checkpoint,
- evaluate the new checkpoint against the baseline,
- append Elo history after each cycle.

That is enough to measure whether the model is moving in the right direction over an hour.

For autonomous operation, the notebook now defaults to `RUN_MODE = "priority_loop"`
so the Colab runtime continuously executes the priority-scored queue.

## How to use in Colab

### Option 1: From GitHub

1. Push this repository to GitHub.
2. Open `notebooks/hex6_colab_fast_bootstrap.ipynb` in Colab.
3. Set `REPO_MODE = "git"` and use `https://github.com/Stroudmj00/hex6-bot.git`.
4. Run the notebook cells.
5. In a local terminal, watch status with:

```powershell
.venv\Scripts\python -m hex6.integration.watch_status --config configs/colab.toml --run-id latest
```

The notebook prints the exact watch command for the generated `RUN_ID`. When a
job uses a config whose default `status_backend` is `none`, the notebook passes
`--status-backend github_branch` automatically when `HEX6_GITHUB_TOKEN` is
available.

Runtime safety defaults:

- `REQUIRE_COLAB = True` to fail fast outside Colab.
- `REQUIRE_GPU = True` to fail fast when no CUDA GPU is attached.

### Option 2: From Google Drive

1. Upload the repository folder to Google Drive.
2. Open the notebook in Colab.
3. Set `REPO_MODE = "drive"` and point `DRIVE_REPO_PATH` at the folder.
4. Run the notebook cells.

## What the notebook does

- mounts Drive if needed,
- clones or copies the repo into `/content`,
- installs the package in editable mode,
- prints CUDA availability,
- runs one of:

```bash
python -m hex6.train.run_bootstrap --config configs/colab.toml --output artifacts/bootstrap_colab
```

or:

```bash
python -m hex6.train.run_cycle --config configs/colab_hour.toml --output-root artifacts/bootstrap_colab_hour --minutes 60
```

```bash
python -m hex6.eval.run_search_matrix --matrix configs/experiments/search_matrix.toml --output artifacts/search_matrix_colab --run-id <run-id> --status-backend github_branch
```

```bash
python -m hex6.eval.run_tournament --config configs/fast.toml --output artifacts/tournament_colab --games-per-match 2 --max-game-plies 48 --max-checkpoints 3 --checkpoint-glob "artifacts/**/bootstrap_model.pt" --include-baseline --include-random --run-id <run-id> --status-backend github_branch
```

or (priority-scored queue loop):

```bash
python -m hex6.integration.run_priority_loop --queue configs/colab_job_queue.toml --state artifacts/colab_queue/state.json --status-backend github_branch
```

- copies the resulting artifacts back to Drive if Drive mode is enabled.
- writes progress to `artifacts/bootstrap_colab/progress.json` for training jobs.
- writes a GitHub-backed status document to the `colab-status` branch when
  `HEX6_GITHUB_TOKEN` is available.
- writes `arena.json` and `elo_history.json` when evaluation is enabled.
- writes `summary.json` for search-matrix and tournament eval jobs.
- for priority-loop mode, writes queue state to `artifacts/colab_queue/state.json`.

## Priority Queue Mode

Use `configs/colab_job_queue.toml` to define jobs with explicit numeric
`priority` scores. The scheduler always picks the highest-priority runnable job
(respecting each job's `min_interval_minutes`). To avoid starvation, each job can
set `max_consecutive_runs`; when the cap is reached and another job is eligible,
the runner yields to the next-priority job.

Default queue priorities:

- `cycle_main`: `100`
- `tournament_regression`: `80` (`max_game_plies = 100`)
- `search_matrix_regression`: `65`
- `bootstrap_refresh`: `50`

## Current local validation

The project has already been validated locally with both a fast and a medium profile.

The medium profile produced:

- `artifacts/bootstrap_colab_test/bootstrap_model.pt`
- `artifacts/bootstrap_colab_test/metrics.json`
- `artifacts/bootstrap_colab_test/progress.json`

## Important limitation

Colab will accelerate the model training and later batched inference, but pure Python
self-play/search is still the main cost right now. The next optimization pass should reduce
search cost before we scale up training volume.

## Parallel runs guidance

Running multiple training runs in the same Colab runtime usually does **not** improve total
throughput for this project:

- runs contend for one GPU, shared CPU, RAM, and disk bandwidth,
- each run gets fewer resources, so wall-clock time per run increases,
- OOM and instability risk goes up.

Better pattern:

- keep one training job per runtime,
- parallelize within that job (`self_play_workers`, data-loader workers, batched inference),
- run additional experiments only if you can use separate runtimes and still stay within Colab
  usage and policy limits.
- if you need guaranteed parallel capacity, move those jobs to Colab Enterprise or dedicated
  cloud VMs instead of relying on dynamic shared runtimes.

For autonomous sweeps, treat Colab as the heavy-compute lane and keep the local
machine limited to `watch_status`, the website, and lightweight coding tasks.
