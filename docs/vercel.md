# Vercel Deployment

## What is prepared

- Root Flask entry point in `app.py`.
- Build helper in `build.py` that copies web assets into `public/static`.
- `requirements.txt` for package installation.
- `pyproject.toml` build hook for Vercel.

## Expected deployment model

- Python serverless function serves the Flask app.
- Static assets are copied into `public/static` during the Vercel build.
- The app uses `configs/play.toml` by default.
- If `HEX6_WEB_CHECKPOINT` is not set, the root `app.py` will try to auto-discover the latest `best_checkpoint` from `artifacts/**/cycle_summary.json`, then fall back to the newest `artifacts/**/bootstrap_model.pt`.

## Optional environment variables

- `HEX6_WEB_CONFIG`: override the play config path.
- `HEX6_WEB_CHECKPOINT`: explicit checkpoint path for the main published bot.
- `HEX6_WEB_OPPONENT_CHECKPOINT`: optional spectator opponent checkpoint.

## Local checks before deploy

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\ruff check .
.venv\Scripts\python build.py
```

## Create the project

If the Vercel CLI is authenticated:

```powershell
npx vercel
```

For a production deploy after the project is linked:

```powershell
npx vercel --prod
```

## Notes

- The current deployment target is the website/play experience, not the training pipeline.
- Training artifacts and Colab status files should stay off the public website path.
- The current app keeps live game sessions in process memory. That is fine for a single long-lived process, but it is not a strong fit for stateless serverless fanout. For fully reliable public interactive play, prefer a stateful host or add a shared session store.
