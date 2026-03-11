"""Optional experiment tracking helpers for local and Colab runs."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import os
from pathlib import Path
from typing import Any

from hex6.config import AppConfig


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _sanitize(value: Any) -> Any:
    if is_dataclass(value):
        return _sanitize(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class NullExperimentTracker:
    enabled = False

    def log(self, payload: dict[str, object], *, step: int | None = None) -> None:
        del payload, step

    def update_summary(self, payload: dict[str, object]) -> None:
        del payload

    def finish(self, *, exit_code: int = 0, summary: dict[str, object] | None = None) -> None:
        del exit_code, summary


class WandbExperimentTracker:
    enabled = True

    def __init__(self, run: Any) -> None:
        self._run = run

    def log(self, payload: dict[str, object], *, step: int | None = None) -> None:
        self._run.log(_sanitize(payload), step=step)

    def update_summary(self, payload: dict[str, object]) -> None:
        for key, value in _sanitize(payload).items():
            self._run.summary[key] = value

    def finish(self, *, exit_code: int = 0, summary: dict[str, object] | None = None) -> None:
        if summary:
            self.update_summary(summary)
        self._run.finish(exit_code=exit_code)


def build_experiment_tracker(
    config: AppConfig,
    *,
    config_path: str,
    output_dir: str | Path,
    run_id: str,
    job_type: str,
) -> NullExperimentTracker | WandbExperimentTracker:
    if not _is_truthy(os.environ.get("HEX6_ENABLE_WANDB")):
        return NullExperimentTracker()

    import wandb

    output_path = Path(output_dir)
    wandb_dir = Path(os.environ.get("WANDB_DIR", output_path / "_wandb"))
    wandb_dir.mkdir(parents=True, exist_ok=True)
    tags = [
        tag.strip()
        for tag in os.environ.get("HEX6_WANDB_TAGS", "").split(",")
        if tag.strip()
    ]
    run = wandb.init(
        project=os.environ.get("HEX6_WANDB_PROJECT", config.project.name),
        entity=os.environ.get("HEX6_WANDB_ENTITY") or None,
        group=os.environ.get("HEX6_WANDB_GROUP") or None,
        name=os.environ.get("HEX6_WANDB_RUN_NAME") or run_id,
        notes=os.environ.get("HEX6_WANDB_NOTES") or None,
        mode=os.environ.get("HEX6_WANDB_MODE", "offline"),
        dir=str(wandb_dir),
        tags=tags,
        job_type=job_type,
        config=_sanitize(
            {
                "project": config.project,
                "runtime": config.runtime,
                "game": config.game,
                "prototype": config.prototype,
                "search": config.search,
                "training": config.training,
                "model": config.model,
                "scoring": config.scoring,
                "heuristic": config.heuristic,
                "integration": config.integration,
                "evaluation": config.evaluation,
                "config_path": config_path,
                "output_dir": str(output_path),
                "run_id": run_id,
            }
        ),
    )
    return WandbExperimentTracker(run)
