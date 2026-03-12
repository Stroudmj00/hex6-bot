# Vercel Deployment

## What is prepared

- Root Flask entry point in `app.py`.
- Build helper in `build.py` that copies web assets into `public/static`.
- `requirements.txt` trimmed to runtime dependencies only.
- `pyproject.toml` build hook for Vercel.
- Bundled production checkpoint at `models/production/hex6_champion.pt`.

## Expected deployment model

- Python serverless function serves the Flask app.
- Static assets are copied into `public/static` during the Vercel build.
- The app uses `configs/play.toml` by default.
- If `HEX6_WEB_CHECKPOINT` is not set, the root `app.py` first uses the bundled production checkpoint at `models/production/hex6_champion.pt`, then falls back to artifact auto-discovery for local/dev use.
- The public UI now exposes four lanes:
  - `Play vs Champion` (hosted strongest model)
  - `Play vs Browser AI` (client-side fallback)
  - `Play vs Friend`
  - `Watch Engine Match`

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
- The current app keeps live game sessions in process memory. That is acceptable for demos, but it is not a strong fit for stateless serverless fanout. For fully reliable public engine-backed play, the next production upgrade is either:
  - a shared session store, or
  - a stateless `analyze-turn` API that accepts full game state from the client.
- The bundled production checkpoint is the current champion. If you later promote a new model, replace `models/production/hex6_champion.pt` and redeploy.

## Recommended deploy flow

1. Run local validation:

```powershell
.venv\Scripts\python -m pytest tests/test_web_app.py
.venv\Scripts\ruff check src tests
.venv\Scripts\python build.py
```

2. Preview locally:

```powershell
.venv\Scripts\python -m hex6.web.run_server --config configs/play.toml --checkpoint models/production/hex6_champion.pt --host 127.0.0.1 --port 5000
```

3. Build and deploy:

```powershell
npx vercel
npx vercel --prod
```
