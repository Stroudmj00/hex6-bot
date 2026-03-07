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
