# Tooling Guide

## Core local commands

### Website

```powershell
.venv\Scripts\python -m hex6.web.run_server --config configs/play.toml --host 127.0.0.1 --port 5000
```

### One-shot bootstrap training

```powershell
.venv\Scripts\python -m hex6.train.run_bootstrap --config configs/fast.toml --output artifacts/bootstrap_fast
```

### Repeated training/eval cycles

```powershell
.venv\Scripts\python -m hex6.train.run_cycle --config configs/colab_hour.toml --output-root artifacts/bootstrap_colab_hour --minutes 60
```

### Watch Colab status

```powershell
.venv\Scripts\python -m hex6.integration.watch_status --config configs/colab_hour.toml --run-id latest
```

### Checkpoint vs baseline arena

```powershell
.venv\Scripts\python -m hex6.eval.run_arena --config configs/colab.toml --checkpoint artifacts/bootstrap_fast/bootstrap_model.pt --output artifacts/arena
```

### Search variant matrix

```powershell
.venv\Scripts\python -m hex6.eval.run_search_matrix --matrix configs/experiments/search_matrix.toml --output artifacts/search_matrix
```

## Deployment

### Local Vercel build check

```powershell
.venv\Scripts\python build.py
```

### Production deploy

```powershell
vercel --prod --yes
```

## Verification

### Lint

```powershell
.venv\Scripts\ruff check .
```

### Test suite

```powershell
.venv\Scripts\python -m pytest
```
