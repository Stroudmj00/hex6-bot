"""Vercel entry point for the Hex6 web app."""

from __future__ import annotations

import json
import os
from pathlib import Path

from hex6.web import create_app


def _resolve_web_config() -> str:
    return os.getenv("HEX6_WEB_CONFIG", "configs/play.toml")


def _resolve_bundled_production_checkpoint(root: Path) -> str | None:
    bundled = _resolve_repo_relative_path(root, "models/production/hex6_champion.pt")
    return None if bundled is None else str(bundled)


def _resolve_checkpoint_from_env_or_artifacts(root: Path) -> str | None:
    explicit = os.getenv("HEX6_WEB_CHECKPOINT", "").strip()
    if explicit:
        resolved = _resolve_repo_relative_path(root, explicit)
        if resolved is not None:
            return str(resolved)

    bundled = _resolve_bundled_production_checkpoint(root)
    if bundled is not None:
        return bundled

    cycle_summaries = _safe_sorted_by_mtime(root.glob("artifacts/**/cycle_summary.json"))
    for summary_path in cycle_summaries:
        try:
            payload = json.loads(summary_path.read_text(encoding="ascii"))
        except (OSError, json.JSONDecodeError):
            continue
        best_checkpoint = payload.get("best_checkpoint")
        if isinstance(best_checkpoint, str):
            resolved = _resolve_repo_relative_path(root, best_checkpoint)
            if resolved is not None:
                return str(resolved)

    checkpoints = _safe_sorted_by_mtime(root.glob("artifacts/**/bootstrap_model.pt"))
    if checkpoints:
        return str(checkpoints[0].resolve())
    return None


def _resolve_opponent_checkpoint(root: Path) -> str | None:
    explicit = os.getenv("HEX6_WEB_OPPONENT_CHECKPOINT", "").strip()
    if not explicit:
        return None
    resolved = _resolve_repo_relative_path(root, explicit)
    return None if resolved is None else str(resolved)


def _resolve_repo_relative_path(root: Path, raw_path: str) -> Path | None:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    if candidate.exists():
        return candidate
    return None


def _safe_sorted_by_mtime(paths) -> list[Path]:
    stamped: list[tuple[float, Path]] = []
    for path in paths:
        try:
            stamped.append((path.stat().st_mtime, path))
        except OSError:
            continue
    stamped.sort(key=lambda item: item[0], reverse=True)
    return [path for _, path in stamped]


_ROOT = Path(__file__).resolve().parent
app = create_app(
    _resolve_web_config(),
    checkpoint_path=_resolve_checkpoint_from_env_or_artifacts(_ROOT),
    spectator_opponent_checkpoint=_resolve_opponent_checkpoint(_ROOT),
)
