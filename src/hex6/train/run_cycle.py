"""Run repeated bootstrap/evaluation cycles for a time budget or cycle count."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import traceback

from hex6.config import load_config
from hex6.eval import append_elo_history, evaluate_checkpoint_against_baseline
from hex6.integration import build_status_publisher
from hex6.train.bootstrap import train_bootstrap


def main() -> None:
    parser = argparse.ArgumentParser(description="Run repeated Hex6 training cycles.")
    parser.add_argument(
        "--config",
        default="configs/colab.toml",
        help="Path to the TOML config file.",
    )
    parser.add_argument(
        "--output-root",
        default="artifacts/bootstrap_cycle",
        help="Root directory where cycle outputs will be written.",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=None,
        help="Maximum number of cycles to run.",
    )
    parser.add_argument(
        "--minutes",
        type=float,
        default=None,
        help="Approximate time budget in minutes.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Explicit run id for status publishing.",
    )
    parser.add_argument(
        "--status-backend",
        default=None,
        help="Override the configured status backend.",
    )
    parser.add_argument(
        "--start-checkpoint",
        default=None,
        help="Optional checkpoint to warm-start the first cycle.",
    )
    args = parser.parse_args()

    if args.cycles is None and args.minutes is None:
        parser.error("provide --cycles or --minutes")

    config = load_config(args.config)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    status = build_status_publisher(
        config,
        config_path=args.config,
        output_dir=str(output_root),
        run_id=args.run_id,
        backend_override=args.status_backend,
    )
    print(
        json.dumps(
            {
                "run_id": status.run_id,
                "status_backend": status.backend,
                "status_target": status.target_description(),
            },
            indent=2,
        )
    )

    start_time = time.monotonic()
    time_budget_seconds = None if args.minutes is None else args.minutes * 60.0
    latest_checkpoint = args.start_checkpoint
    cycle_index = 1
    summaries: list[dict[str, object]] = []

    try:
        while should_continue(cycle_index, args.cycles, start_time, time_budget_seconds):
            cycle_dir = output_root / f"cycle_{cycle_index:03d}"
            cycle_dir.mkdir(parents=True, exist_ok=True)
            cycle_callback = build_cycle_callback(status.publish if status.enabled else None, cycle_index)
            metrics = train_bootstrap(
                config,
                output_dir=cycle_dir,
                config_path=args.config,
                progress_callback=cycle_callback,
                final_stage="cycle_training_complete",
                init_checkpoint_path=latest_checkpoint,
            )
            cycle_summary: dict[str, object] = {
                "cycle_index": cycle_index,
                "started_at": utc_now(),
                "metrics": metrics,
            }
            if config.evaluation.arena_games > 0:
                arena = evaluate_checkpoint_against_baseline(
                    checkpoint_path=metrics["checkpoint"],
                    config=config,
                    output_dir=cycle_dir,
                    progress_callback=cycle_callback,
                )
                cycle_summary["arena"] = arena
                append_elo_history(output_root / "elo_history.json", arena)

            latest_checkpoint = str(metrics["checkpoint"])
            cycle_summary["latest_checkpoint"] = latest_checkpoint
            summaries.append(cycle_summary)
            write_cycle_root_summary(output_root, summaries, latest_checkpoint)
            if status.enabled:
                payload = {
                    "stage": "cycle_complete",
                    "cycle_index": cycle_index,
                    "cycles_completed": len(summaries),
                    "latest_checkpoint": latest_checkpoint,
                    "summary_path": str(output_root / "cycle_summary.json"),
                }
                if "arena" in cycle_summary:
                    payload["latest_elo"] = cycle_summary["arena"]["final_elo_a"]
                    payload["latest_win_rate"] = cycle_summary["arena"]["win_rate_a"]
                status.publish(payload)
            cycle_index += 1
    except Exception as exc:
        if status.enabled:
            status.publish(
                {
                    "stage": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
        raise

    final_summary = {
        "cycles_completed": len(summaries),
        "latest_checkpoint": latest_checkpoint,
        "summary_path": str(output_root / "cycle_summary.json"),
        "elo_history_path": str(output_root / "elo_history.json"),
    }
    if summaries and "arena" in summaries[-1]:
        final_summary["latest_elo"] = summaries[-1]["arena"]["final_elo_a"]
        final_summary["latest_win_rate"] = summaries[-1]["arena"]["win_rate_a"]
    if status.enabled:
        status.publish({"stage": "complete", **final_summary})
    print(json.dumps(final_summary, indent=2))


def build_cycle_callback(publish, cycle_index: int):
    if publish is None:
        return None

    def callback(payload: dict[str, object]) -> None:
        publish({"cycle_index": cycle_index, **payload})

    return callback


def should_continue(
    cycle_index: int,
    max_cycles: int | None,
    start_time: float,
    time_budget_seconds: float | None,
) -> bool:
    if max_cycles is not None and cycle_index > max_cycles:
        return False
    if time_budget_seconds is None:
        return True
    if cycle_index == 1:
        return True
    return (time.monotonic() - start_time) < time_budget_seconds


def write_cycle_root_summary(
    output_root: Path,
    summaries: list[dict[str, object]],
    latest_checkpoint: str | None,
) -> None:
    payload = {
        "generated_at": utc_now(),
        "cycles_completed": len(summaries),
        "latest_checkpoint": latest_checkpoint,
        "cycles": summaries,
    }
    (output_root / "cycle_summary.json").write_text(json.dumps(payload, indent=2), encoding="ascii")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    main()
