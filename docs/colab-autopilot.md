# Colab Autopilot

This workflow sets up a simple division of labor:

- Codex or another local judge submits repo-backed Colab job requests.
- A Colab worker claims and executes those requests.
- While the GPU is busy, a second AI can claim a research idea from the backlog and produce the next engine-improvement proposal.

The current implementation is file-backed and repo-native. It does not depend on a separate service.

## Will Leaving It Running Create A Super Strong Bot?

Not by itself. The current autopilot can keep Colab busy and can return checkpoints, but strength only compounds when every run is part of a closed promotion loop:

1. Train from the current validated champion, not from a random or stale checkpoint.
2. Save artifacts durably before Colab can recycle `/content`.
3. Evaluate every returned checkpoint against the current champion and baseline probes.
4. Promote only checkpoints that pass the configured ladder or promotion gates.
5. Feed the promoted checkpoint back into the next training request.
6. Track failed, draw-heavy, or ambiguous runs as evidence and convert them into targeted follow-up jobs instead of treating them as progress.

If any of those links is missing, unattended Colab time can produce lots of files without producing a stronger bot. The most common failure modes are:

- The worker runs with a credential-dependent status backend and exits before training.
- The runtime writes useful checkpoints only under ephemeral `/content` and then disconnects.
- A cycle returns a checkpoint, but no ladder or promotion decision updates the champion.
- The queue keeps launching similar cycles after the evaluation gate has saturated.
- The model overfits the current promotion lane and remains weak on defend-first or draw-heavy positions.

The target setup is a judge-controlled loop:

1. Keep `models/production/hex6_champion.pt` as the current production champion.
2. Submit Colab cycle jobs seeded with `--start-checkpoint models/production/hex6_champion.pt`.
3. When a cycle returns `best_checkpoint`, write a ladder manifest entry for that exact checkpoint.
4. Run one ladder job with `configs/colab_ladder.toml`.
5. If the ladder promotes the checkpoint, update the production champion in a tracked change with the promotion evidence.
6. If the ladder rejects it, archive the result and submit a targeted follow-up job based on the failure signal.

That loop can improve the bot over time. "Run training forever" cannot be trusted without the promotion, artifact, and feedback steps.

## Goal Startup Checklist

Use this checklist when starting or resuming the Colab autopilot goal:

Start the Codex goal with:

```text
/goal Operate the Hex6 Colab autopilot loop: keep Colab busy with the highest-value pending job requests, use local work for code/tests/research while compute runs, and judge each returned Colab result as ladder submission, follow-up request, or archived evidence.
```

1. Confirm the active objective is to keep Colab busy, use local time for research or small validation, and judge every returned result as ladder, follow-up, or archive.
2. Run the local list command first:

```powershell
.venv\Scripts\python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml list
```

3. If there is no useful pending request, submit the highest-value cycle or ladder request from the local judge.
4. Publish pending local requests to the shared queue branch with `publish-requests` so Colab can fetch them from a fresh clone.
5. For meaningful training, mount Drive and run from `/content/drive/MyDrive/Hex6-Colab/hex6-bot` before submitting or claiming work. If Colab Drive mount fails, use the GitHub artifact/request branch fallback instead of relying on ephemeral `/content`.
6. Run the autopilot storage preflight before any long worker claim. If the request writes under `/content/drive`, a failed preflight means Drive is not mounted durably and the worker must not start expensive training.
7. Configure `HEX6_GITHUB_TOKEN` in Colab Secrets when Drive is unreliable. The token resolver checks Colab Secrets, then environment variables, then `gh auth token`; the worker fetches shared requests and uploads result bundles to the `colab-autopilot-artifacts` branch.
8. In Colab, switch to a T4 runtime before claiming T4-gated work, then verify with `nvidia-smi`.
9. Run exactly one worker claim with `scripts/colab_run.py autopilot-worker --once`.
10. While Colab runs, claim or complete one research idea locally instead of running long local training.
11. When Colab returns a result under `artifacts/colab_autopilot/results/`, run `judge-result` before launching more compute.
12. If a checkpoint is found, do not call it stronger until a promotion or ladder gate proves it against the current champion.

## Files

- `configs/colab_autopilot.toml`: broker paths and polling defaults.
- `configs/colab_research_backlog.toml`: ranked research ideas for idle AI time.
- `src/hex6/integration/run_autopilot.py`: submit, list, worker, and research commands.
- `scripts/colab_run.py`: Colab wrapper with `ladder` and `autopilot-worker` commands.
- `scripts/colab_autopilot_monitor.py`: read-only queue/progress/result/log monitor for Colab.
- `notebooks/hex6_colab_autopilot.ipynb`: fixed-cell Colab launcher and monitor notebook.

## Local Judge Flow

Submit a training request:

```powershell
.venv\Scripts\python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml submit --kind cycle --priority 90 --config configs/colab_strongest_v2.toml --output-root artifacts/bootstrap_colab_strongest_v2 --minutes 60 --notes "One-hour strongest-v2 cycle"
```

Submit a ladder request:

```powershell
.venv\Scripts\python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml submit --kind ladder --priority 95 --config configs/colab_ladder.toml --manifest artifacts/colab_ladder/submissions.toml --output artifacts/colab_ladder --state artifacts/colab_ladder/state.json --ledger artifacts/colab_ladder/strength_ledger.jsonl --max-submissions 1 --notes "Process one pending challenger"
```

Inspect queue and research state:

```powershell
.venv\Scripts\python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml list
```

Claim the next research idea and print a prompt for another AI:

```powershell
.venv\Scripts\python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml next-research --researcher-id codex-research-01
```

Mark a research idea complete:

```powershell
.venv\Scripts\python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml complete-research --idea-id IDEA-001 --note-path artifacts/colab_autopilot/research_notes/IDEA-001.md
```

Judge a returned training result and submit a one-candidate ladder request when the checkpoint is present:

```powershell
.venv\Scripts\python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml judge-result --result artifacts/colab_autopilot/results/<request-id>.json --submit-ladder
```

When Drive mount is unavailable, bundle a returned result before the Colab runtime can recycle. The worker writes this bundle automatically after completion; this command lets you recreate it manually:

```powershell
.venv\Scripts\python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml export-result --result artifacts/colab_autopilot/results/<request-id>.json --repo-root .
```

Upload a returned result bundle to the configured artifact branch:

```powershell
.venv\Scripts\python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml upload-result --result artifacts/colab_autopilot/results/<request-id>.json --repo-root .
```

Fetch and import a Colab result bundle back into the local judge state:

```powershell
.venv\Scripts\python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml fetch-result --request-id <request-id> --import-bundle --repo-root .
```

Publish local pending requests to the shared request queue:

```powershell
.venv\Scripts\python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml publish-requests
```

Dry-run a production champion promotion after a ladder request returns:

```powershell
.venv\Scripts\python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml promote-champion --summary artifacts/colab_ladder/autopilot/<request-id>/ladder_summary.json
```

Apply the production champion update only when the dry run reports `decision = "promote_champion"` and the evidence matches the intended candidate:

```powershell
.venv\Scripts\python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml promote-champion --summary artifacts/colab_ladder/autopilot/<request-id>/ladder_summary.json --apply
```

## Colab Worker Flow

### Current Operator Runbook

Prefer the Colab terminal for active operations. Notebook cells are useful for the fixed launcher, but terminal commands are more reliable for debugging, relaunching, and reading logs.

For anything longer than a tiny debug run, prefer a Drive-backed working copy or copy results to Drive as soon as they are produced. Colab `/content` is ephemeral; disconnected or recycled runtimes can erase both the repo checkout and `artifacts/` before the local judge can inspect them.

If Drive mount fails and you must use `/content`, keep runs short and preserve evidence as a single export bundle. Completed autopilot worker jobs create `artifacts/colab_autopilot/exports/<request-id>.zip` with the result JSON, request JSON, summaries, checkpoint, nearby metrics, and worker log when available. Download or sync that zip before disconnecting.

For unattended no-Drive fallback, set `HEX6_GITHUB_TOKEN` in Colab Secrets before running the worker and enable notebook access for that secret. The broker reads Colab Secrets directly, so you do not need to export the token into the environment. `configs/colab_autopilot.toml` is configured to publish bundles to the separate `colab-autopilot-artifacts` branch. These zips are transport evidence, not source artifacts, and should not be merged into `main`.

The same branch also carries queue state under `colab_autopilot_requests/`. Local operators publish pending requests with `publish-requests`; Colab workers fetch those pending requests before each claim and publish request status transitions back to the branch.

Do not let a Colab claim run unbounded. The broker supports `default_job_timeout_minutes` in `configs/colab_autopilot.toml`, per-request `--timeout-minutes`, and worker-level `--job-timeout-minutes`. A timeout marks the request failed with exit code `124`, writes a result payload, and still attempts to create the export bundle.

If a reconnect probe reports `REPO False` for `/content/hex6-bot/.git`, treat the interrupted job as archived lost-output evidence. Do not promote a checkpoint from that run and do not relaunch meaningful training in `/content` again; switch to a Drive-backed checkout first.

1. Open the notebook URL for the branch you want Colab to run:

```text
https://colab.research.google.com/github/Stroudmj00/hex6-bot/blob/codex/colab-autopilot-temp/notebooks/hex6_colab_autopilot.ipynb
```

2. Manually select a GPU runtime before starting expensive work:

```text
Runtime -> Change runtime type -> Hardware accelerator -> T4 GPU -> Save
```

3. Verify the runtime before claiming a T4 job:

```bash
nvidia-smi
```

If `nvidia-smi` is missing or reports no NVIDIA GPU, do not run the T4-gated worker. Either switch the runtime to T4 first or run only an explicitly CPU-safe debug/inspection command.

4. Clone or update the repo in Colab:

```bash
cd /content
if [ ! -d /content/hex6-bot/.git ]; then
  git clone --branch codex/colab-autopilot-temp --single-branch https://github.com/Stroudmj00/hex6-bot.git /content/hex6-bot
else
  cd /content/hex6-bot
  git fetch origin codex/colab-autopilot-temp
  git checkout codex/colab-autopilot-temp
  git pull --ff-only origin codex/colab-autopilot-temp
fi
cd /content/hex6-bot
python -m pip install -e .
```

Drive-backed form for longer jobs:

```bash
python - <<'PY'
from google.colab import drive
drive.mount('/content/drive')
PY
```

Then run the checkout under a durable directory:

```bash
mkdir -p /content/drive/MyDrive/Hex6-Colab
cd /content/drive/MyDrive/Hex6-Colab
if [ ! -d hex6-bot/.git ]; then
  git clone --branch codex/colab-autopilot-temp --single-branch https://github.com/Stroudmj00/hex6-bot.git hex6-bot
else
  cd hex6-bot
  git fetch origin codex/colab-autopilot-temp
  git checkout codex/colab-autopilot-temp
  git pull --ff-only origin codex/colab-autopilot-temp
  cd ..
fi
cd hex6-bot
python -m pip install -e .
```

5. Inspect queue state:

```bash
python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml list
```

Run a storage preflight before claiming a long job:

```bash
python scripts/colab_run.py autopilot-preflight \
  --repo-root /content/drive/MyDrive/Hex6-Colab/hex6-bot \
  --plan configs/colab_autopilot.toml \
  --minimum-gpu-tier T4
```

The preflight writes and deletes a probe file in the job output directory. If it reports that `/content/drive` is not mounted, mount Drive or switch to a short debug request before running the worker.

6. Submit a small debug cycle when validating the pipeline or instrumentation:

```bash
python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml submit \
  --kind cycle \
  --priority 83 \
  --notes "T4 debug cycle for Colab pipeline and search-metrics evidence." \
  --config configs/colab_t4_debug.toml \
  --output-root artifacts/bootstrap_colab_t4_debug_metrics \
  --cycles 1
```

7. Run one T4-gated worker:

```bash
python scripts/colab_run.py autopilot-worker \
  --repo-root /content/hex6-bot \
  --plan configs/colab_autopilot.toml \
  --worker-id colab-t4-01 \
  --status-backend none \
  --job-timeout-minutes 120 \
  --minimum-gpu-tier T4 \
  --once
```

The autopilot plan defaults to `status_backend = "none"` so Colab can run without GitHub credentials. Use `github_branch` only when `HEX6_GITHUB_TOKEN` or another authenticated GitHub path is configured in the runtime.

8. Monitor from another terminal command or rerun after the worker exits:

```bash
python scripts/colab_autopilot_monitor.py \
  --repo-root /content/hex6-bot \
  --worker-state artifacts/colab_autopilot/worker_state.json \
  --worker-log artifacts/colab_autopilot/worker.log \
  --tail-lines 160
```

Progress stages before self-play are diagnostic. `starting` should move quickly to `selecting_device`, `loading_model`, `loading_replay_buffer` when a replay buffer exists, then `starting_self_play`. Once AlphaZero self-play begins, `self_play_heartbeat` should appear before the first root-analysis batch. A run that stays at `loading_model` points at checkpoint/model load; a run that stays at `starting_self_play` or `self_play_heartbeat` points at search/self-play.

9. Inspect returned result and metrics:

```bash
python - <<'PY'
import json
from pathlib import Path

root = Path("/content/hex6-bot/artifacts/bootstrap_colab_t4_debug_metrics")
metrics_path = root / "cycle_001" / "metrics.json"
summary_path = root / "cycle_summary.json"

if summary_path.exists():
    print(json.dumps(json.loads(summary_path.read_text(encoding="ascii")), indent=2))
if metrics_path.exists():
    metrics = json.loads(metrics_path.read_text(encoding="ascii"))
    print(json.dumps({
        "device": metrics.get("device"),
        "examples": metrics.get("examples"),
        "self_play_seconds": metrics.get("self_play_seconds"),
        "training_seconds": metrics.get("training_seconds"),
        "total_seconds": metrics.get("total_seconds"),
        "resource_summary": metrics.get("resource_summary", {}),
        "self_play_search_metrics": metrics.get("self_play_search_metrics", {}),
    }, indent=2))
PY
```

10. Judge the result:

- Promote to ladder only when the checkpoint came from a meaningful training/eval profile and has explicit promotion or ladder evidence.
- Submit a follow-up Colab request when the result exposes a specific next experiment or failure boundary.
- Archive as evidence only when the run is a tiny debug, CPU fallback, failed `SIGKILL`, or instrumentation probe with no strength evidence.

Do not commit anything under `artifacts/`. Returned Colab payloads are evidence for decisions, not source files.

If Drive is unavailable but artifact upload is configured, recover the completed run locally:

```powershell
.venv\Scripts\python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml fetch-result --request-id <request-id> --import-bundle --repo-root .
.venv\Scripts\python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml judge-result --result artifacts/colab_autopilot/results/<request-id>.json --submit-ladder
```

Notebook form:

1. Open `notebooks/hex6_colab_autopilot.ipynb` in Colab.
2. Connect a GPU runtime.
3. Run the cells from top to bottom.
4. Rerun the monitor cell to inspect request, progress, result, and worker log state.

The notebook starts the worker as a background process and writes stdout/stderr to `artifacts/colab_autopilot/worker.log`.

Direct module form:

```bash
cd /content/drive/MyDrive/Hex-A-Toe
python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml worker --repo-root /content/drive/MyDrive/Hex-A-Toe --worker-id colab-t4-01 --once
```

Wrapper form through the existing Colab helper:

```bash
cd /content/drive/MyDrive/Hex-A-Toe
python scripts/colab_run.py autopilot-worker --repo-root /content/drive/MyDrive/Hex-A-Toe --minimum-gpu-tier T4 --plan configs/colab_autopilot.toml --worker-id colab-t4-01 --once
```

Run a manifest-driven ladder directly from Colab:

```bash
cd /content/drive/MyDrive/Hex-A-Toe
python scripts/colab_run.py ladder --repo-root /content/drive/MyDrive/Hex-A-Toe --minimum-gpu-tier T4 --config configs/colab_ladder.toml --manifest artifacts/colab_ladder/submissions.toml --output artifacts/colab_ladder --max-submissions 1
```

Completed requests write a machine-readable result file under `artifacts/colab_autopilot/results/`. Training jobs also emit a suggested ladder submission payload when a checkpoint is found.

Monitor an active runtime:

```bash
python scripts/colab_autopilot_monitor.py --repo-root /content/hex6-bot --tail-lines 80
```

## Operator Prompt

Send this to a second AI if you want it to run the plan:

```text
You are the Hex6 Colab autopilot operator inside the repository at C:\Hexagonal tic tac toe.

Mission:
1. Keep Google Colab busy with the highest-value pending job requests.
2. While Colab is running, claim the top pending research idea and produce one concrete engine-improvement proposal.
3. When a Colab job finishes, inspect the returned result payload and decide whether it should become a ladder submission, a follow-up Colab request, or just a research note.

Read first:
- README.md
- AGENTS.md
- docs/index.md
- docs/architecture.md
- docs/tools.md
- docs/colab-autopilot.md

Primary commands:
- Submit requests: python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml submit ...
- List state: python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml list
- Preflight next request: python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml preflight --repo-root <repo-root>
- Publish pending requests: python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml publish-requests
- Fetch result bundle: python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml fetch-result --request-id <request-id> --import-bundle --repo-root <repo-root>
- Claim research: python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml next-research --researcher-id codex-research-01
- Colab worker: python -m hex6.integration.run_autopilot --plan configs/colab_autopilot.toml worker --repo-root <repo-root> --worker-id <worker-id> --once

Rules:
- Keep behavior config-first.
- Do not run long local training.
- Use Colab for expensive compute and local runs only for tests and small smokes.
- Do not commit anything under artifacts/.
- If you add config knobs, update profiles and tests in the same change.
- Treat Codex as the central judge: write down why each returned checkpoint should or should not enter the ladder.

Loop:
1. Run the list command.
2. If there is no meaningful pending Colab job, create one using the best current idea or evaluation need.
3. If Colab is available, run one worker job.
4. While waiting on compute, claim one research idea and produce a short repo-grounded proposal with code targets and validation steps.
5. When a result file appears under artifacts/colab_autopilot/results, inspect it and decide the next action:
   - promote to ladder manifest
   - submit a follow-up Colab request
   - archive as evidence only

Output style:
- Be concise.
- Prefer direct actions over long plans.
- End each update with the next concrete action.
```
