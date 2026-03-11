# Open-Source Checklist

The repository layout and contributor docs are in place. The remaining items below require project-owner choices rather than code cleanup.

## Required Before Public Release

1. Choose a license and add `LICENSE`.
2. Add final repository URLs to `pyproject.toml` once the public GitHub location exists.
3. Decide whether to publish:
   - `SECURITY.md`
   - a code of conduct
   - GitHub issue templates
4. Enable branch protection and CI in the GitHub repository settings after upload.

## Nice To Have After Initial Release

1. Add badges to `README.md` once CI and the public repo URL exist.
2. Add `CODEOWNERS` if multiple maintainers will review changes.
3. Add issue templates if external contributors start filing bugs/features regularly.
