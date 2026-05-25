# Colab Autopilot

This workflow sets up a simple division of labor:

- Codex or another local judge submits repo-backed Colab job requests.
- A Colab worker claims and executes those requests.
- While the GPU is busy, a second AI can claim a research idea from the backlog and produce the next engine-improvement proposal.

The current implementation is file-backed and repo-native. It does not depend on a separate service.

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

## Colab Worker Flow

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
