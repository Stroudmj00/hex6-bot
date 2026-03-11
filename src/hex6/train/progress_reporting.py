"""Console/status progress helpers for bootstrap and cycle runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import math
import time
from typing import Callable


ProgressSink = Callable[[dict[str, object]], dict[str, object] | None]


def _safe_ratio(numerator: object, denominator: object) -> float:
    try:
        num = float(numerator)
        den = float(denominator)
    except (TypeError, ValueError):
        return 0.0
    if den <= 0.0:
        return 0.0
    return min(max(num / den, 0.0), 1.0)


def evaluation_progress_fraction(payload: dict[str, object]) -> float:
    stage = str(payload.get("stage", ""))
    if stage == "evaluation":
        return _safe_ratio(payload.get("completed_games"), payload.get("total_games"))
    if stage == "tournament":
        return _safe_ratio(payload.get("completed_matches"), payload.get("total_matches"))
    return 0.0


def bootstrap_progress_fraction(payload: dict[str, object], *, include_evaluation: bool) -> float:
    stage = str(payload.get("stage", ""))
    if stage == "starting":
        return 0.0
    if stage == "self_play":
        return 0.7 * _safe_ratio(payload.get("completed_games"), payload.get("total_games"))
    if stage == "dataset_ready":
        return 0.72
    if stage == "training":
        return 0.72 + (0.23 * _safe_ratio(payload.get("epoch"), payload.get("epochs")))
    if stage in {"training_complete", "cycle_training_complete"}:
        return 0.8 if include_evaluation else 1.0
    if stage in {"evaluation", "tournament"}:
        base = 0.8 if include_evaluation else 0.0
        span = 0.2 if include_evaluation else 1.0
        return min(base + (span * evaluation_progress_fraction(payload)), 0.999 if include_evaluation else 1.0)
    if stage in {"cycle_complete", "complete"}:
        return 1.0
    if stage == "failed":
        return min(max(float(payload.get("progress_fraction", 0.0)), 0.0), 1.0)
    return min(max(float(payload.get("progress_fraction", 0.0)), 0.0), 1.0)


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def format_completion_time(moment: datetime | None) -> str:
    if moment is None:
        return "unknown"
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def enrich_progress_payload(
    payload: dict[str, object],
    *,
    started_monotonic: float,
    started_wall_time: datetime,
    fraction: float,
) -> dict[str, object]:
    enriched = dict(payload)
    clipped_fraction = min(max(fraction, 0.0), 1.0)
    elapsed_seconds = max(0.0, time.monotonic() - started_monotonic)
    estimated_total_seconds: float | None = None
    estimated_remaining_seconds: float | None = None
    estimated_completion_time: str | None = None
    if clipped_fraction > 0.0:
        estimated_total_seconds = elapsed_seconds / clipped_fraction
        estimated_remaining_seconds = max(0.0, estimated_total_seconds - elapsed_seconds)
        estimated_completion_time = (
            started_wall_time + timedelta(seconds=estimated_total_seconds)
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    enriched["progress_fraction"] = round(clipped_fraction, 4)
    enriched["progress_percent"] = round(clipped_fraction * 100.0, 1)
    enriched["elapsed_seconds"] = round(elapsed_seconds, 3)
    enriched["estimated_total_seconds"] = None if estimated_total_seconds is None else round(estimated_total_seconds, 3)
    enriched["estimated_remaining_seconds"] = None if estimated_remaining_seconds is None else round(estimated_remaining_seconds, 3)
    enriched["estimated_completion_time"] = estimated_completion_time
    return enriched


def print_progress_line(payload: dict[str, object]) -> None:
    stage = str(payload.get("stage", ""))
    parts = ["[progress]"]
    if "cycle_index" in payload:
        parts.append(f"cycle={payload['cycle_index']}")
    cycle_phase = payload.get("cycle_phase")
    if cycle_phase:
        parts.append(f"phase={cycle_phase}")
    parts.append(f"stage={stage}")
    if "progress_percent" in payload:
        parts.append(f"progress={payload['progress_percent']:.1f}%")
    if "cycle_progress_percent" in payload:
        parts.append(f"cycle_progress={float(payload['cycle_progress_percent']):.1f}%")
    if "run_progress_percent" in payload:
        parts.append(f"run_progress={float(payload['run_progress_percent']):.1f}%")
    if "completed_games" in payload and "total_games" in payload:
        parts.append(f"games={payload['completed_games']}/{payload['total_games']}")
    if "completed_matches" in payload and "total_matches" in payload:
        parts.append(f"matches={payload['completed_matches']}/{payload['total_matches']}")
    if "epoch" in payload and "epochs" in payload:
        parts.append(f"epoch={payload['epoch']}/{payload['epochs']}")
    if "estimated_remaining_seconds" in payload:
        parts.append(f"eta={format_duration(payload.get('estimated_remaining_seconds'))}")
    if "estimated_completion_time" in payload:
        completion_text = payload.get("estimated_completion_time")
        if isinstance(completion_text, str):
            parts.append(f"eta_at={completion_text}")
    print(" ".join(parts))


@dataclass
class BootstrapProgressReporter:
    publish: ProgressSink | None
    include_evaluation: bool
    started_monotonic: float = field(default_factory=time.monotonic)
    started_wall_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def handle(self, payload: dict[str, object]) -> dict[str, object]:
        enriched = enrich_progress_payload(
            payload,
            started_monotonic=self.started_monotonic,
            started_wall_time=self.started_wall_time,
            fraction=bootstrap_progress_fraction(payload, include_evaluation=self.include_evaluation),
        )
        if self.publish is not None:
            self.publish(enriched)
        print_progress_line(enriched)
        return enriched


@dataclass
class CycleProgressReporter:
    publish: ProgressSink | None
    max_cycles: int | None
    time_budget_seconds: float | None
    started_monotonic: float = field(default_factory=time.monotonic)
    started_wall_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    current_cycle_index: int | None = None
    current_cycle_started_monotonic: float | None = None
    completed_cycle_durations: list[float] = field(default_factory=list)
    completed_cycle_indices: set[int] = field(default_factory=set)

    def handle(self, payload: dict[str, object]) -> dict[str, object]:
        raw_cycle_index = payload.get("cycle_index")
        cycle_index = int(raw_cycle_index) if isinstance(raw_cycle_index, int) or isinstance(raw_cycle_index, float) else self.current_cycle_index or 1
        if self.current_cycle_index != cycle_index:
            self.current_cycle_index = cycle_index
            self.current_cycle_started_monotonic = time.monotonic()

        cycle_fraction = self._cycle_fraction(payload)
        elapsed_total = max(0.0, time.monotonic() - self.started_monotonic)
        run_fraction, completion_time, remaining_seconds = self._run_estimate(
            cycle_index=cycle_index,
            cycle_fraction=cycle_fraction,
            elapsed_total=elapsed_total,
        )

        enriched = dict(payload)
        enriched["cycle_progress_fraction"] = round(cycle_fraction, 4)
        enriched["cycle_progress_percent"] = round(cycle_fraction * 100.0, 1)
        enriched["run_progress_fraction"] = round(run_fraction, 4)
        enriched["run_progress_percent"] = round(run_fraction * 100.0, 1)
        enriched["elapsed_seconds"] = round(elapsed_total, 3)
        enriched["estimated_remaining_seconds"] = None if remaining_seconds is None else round(remaining_seconds, 3)
        enriched["estimated_completion_time"] = (
            None
            if completion_time is None
            else completion_time.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )

        if str(payload.get("stage", "")) == "cycle_complete" and cycle_index not in self.completed_cycle_indices:
            if self.current_cycle_started_monotonic is not None:
                self.completed_cycle_durations.append(max(0.0, time.monotonic() - self.current_cycle_started_monotonic))
            self.completed_cycle_indices.add(cycle_index)

        if self.publish is not None:
            self.publish(enriched)
        print_progress_line(enriched)
        return enriched

    def _cycle_fraction(self, payload: dict[str, object]) -> float:
        stage = str(payload.get("stage", ""))
        phase = str(payload.get("cycle_phase", ""))
        if stage in {"cycle_complete", "complete"}:
            return 1.0
        if phase == "training":
            return 0.7 * min(max(float(payload.get("progress_fraction", 0.0)), 0.0), 1.0)
        if phase == "post_train_evaluation":
            return 0.7 + (0.15 * evaluation_progress_fraction(payload))
        if phase == "promotion":
            return 0.85 + (0.15 * evaluation_progress_fraction(payload))
        return min(max(float(payload.get("cycle_progress_fraction", 0.0)), 0.0), 1.0)

    def _run_estimate(
        self,
        *,
        cycle_index: int,
        cycle_fraction: float,
        elapsed_total: float,
    ) -> tuple[float, datetime | None, float | None]:
        estimated_cycle_seconds = self._estimated_cycle_seconds(cycle_fraction)
        total_cycle_estimate: int | None = None
        if self.max_cycles is not None and self.max_cycles > 0:
            total_cycle_estimate = self.max_cycles
        elif self.time_budget_seconds is not None and estimated_cycle_seconds is not None and estimated_cycle_seconds > 0.0:
            total_cycle_estimate = max(cycle_index, math.ceil(self.time_budget_seconds / estimated_cycle_seconds))

        if total_cycle_estimate is None or total_cycle_estimate <= 0:
            if self.time_budget_seconds is not None and self.time_budget_seconds > 0.0:
                budget_fraction = min(max(elapsed_total / self.time_budget_seconds, 0.0), 0.999)
                completion_time = self.started_wall_time + timedelta(seconds=self.time_budget_seconds)
                return budget_fraction, completion_time, max(0.0, self.time_budget_seconds - elapsed_total)
            return 0.0, None, None

        run_fraction = min(max(((cycle_index - 1) + cycle_fraction) / total_cycle_estimate, 0.0), 0.999 if cycle_fraction < 1.0 else 1.0)
        if estimated_cycle_seconds is None:
            return run_fraction, None, None
        estimated_total_seconds = total_cycle_estimate * estimated_cycle_seconds
        completion_time = self.started_wall_time + timedelta(seconds=estimated_total_seconds)
        return run_fraction, completion_time, max(0.0, estimated_total_seconds - elapsed_total)

    def _estimated_cycle_seconds(self, cycle_fraction: float) -> float | None:
        estimates = list(self.completed_cycle_durations)
        if self.current_cycle_started_monotonic is not None and cycle_fraction > 0.05:
            current_elapsed = max(0.0, time.monotonic() - self.current_cycle_started_monotonic)
            estimates.append(current_elapsed / max(cycle_fraction, 1e-6))
        if not estimates:
            return None
        return sum(estimates) / len(estimates)


def build_cycle_phase_callback(
    reporter: CycleProgressReporter,
    *,
    cycle_index: int,
    phase: str,
) -> Callable[[dict[str, object]], None]:
    def callback(payload: dict[str, object]) -> None:
        reporter.handle({"cycle_index": cycle_index, "cycle_phase": phase, **payload})

    return callback
