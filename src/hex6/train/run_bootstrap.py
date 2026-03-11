"""CLI entry point for bootstrap training."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
import traceback

from hex6.config import load_config
from hex6.eval import evaluate_checkpoint_against_baseline, evaluate_checkpoint_with_tournament_gate
from hex6.integration import build_status_publisher
from hex6.train.bootstrap import train_bootstrap
from hex6.train.progress_reporting import BootstrapProgressReporter
from hex6.train.tracking import build_experiment_tracker


def main() -> None:
    parser = argparse.ArgumentParser(description="Run bootstrap training for Hex6.")
    parser.add_argument(
        "--config",
        default="configs/default.toml",
        help="Path to the TOML config file.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/bootstrap",
        help="Directory where checkpoints and metrics will be written.",
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
    args = parser.parse_args()

    config = load_config(args.config)
    if config.evaluation.post_train_eval not in {"arena", "tournament"}:
        raise ValueError(f"unsupported evaluation.post_train_eval: {config.evaluation.post_train_eval}")
    final_training_stage = "training_complete" if config.evaluation.arena_games > 0 else "complete"
    status = build_status_publisher(
        config,
        config_path=args.config,
        output_dir=args.output,
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
    tracker = build_experiment_tracker(
        config,
        config_path=args.config,
        output_dir=args.output,
        run_id=status.run_id,
        job_type="bootstrap",
    )
    tracker.log(
        {
            "stage": "starting",
            "run_id": status.run_id,
            "status_backend": status.backend,
            "status_target": status.target_description(),
        }
    )
    reporter = BootstrapProgressReporter(
        publish=status.publish if status.enabled else None,
        include_evaluation=config.evaluation.arena_games > 0,
        started_monotonic=time.monotonic(),
    )
    try:
        metrics = train_bootstrap(
            config,
            output_dir=args.output,
            config_path=args.config,
            progress_callback=reporter.handle,
            final_stage=final_training_stage,
        )
    except Exception as exc:
        reporter.handle(
            {
                "stage": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
        tracker.finish(
            exit_code=1,
            summary={
                "stage": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        raise

    if config.evaluation.arena_games > 0:
        if config.evaluation.post_train_eval == "tournament":
            post_train = evaluate_checkpoint_with_tournament_gate(
                checkpoint_path=metrics["checkpoint"],
                config=config,
                config_path=args.config,
                output_dir=args.output,
                include_baseline=True,
                include_random=False,
                progress_callback=reporter.handle,
            )
        else:
            arena = evaluate_checkpoint_against_baseline(
                checkpoint_path=metrics["checkpoint"],
                config=config,
                output_dir=args.output,
                progress_callback=reporter.handle,
            )
            metrics["arena"] = arena
            post_train = {
                "kind": "arena",
                "leader": arena["agent_a"]["name"],
                "games": arena["games"],
                "max_game_plies": config.evaluation.max_game_plies,
                "draw_rate": arena["draw_rate"],
                "checkpoint_name": arena["agent_a"]["name"],
                "checkpoint_rank": 1,
                "checkpoint_points": arena["score_a"],
                "checkpoint_win_rate": arena["win_rate_a"],
                "checkpoint_wins": arena["wins_a"],
                "checkpoint_losses": arena["wins_b"],
                "checkpoint_draws": arena["draws"],
                "summary_path": arena["arena_path"],
                "history_path": arena["elo_history_path"],
            }
        metrics["post_train_evaluation"] = post_train
        metrics_path = Path(args.output) / "metrics.json"
        metrics_path.write_text(json.dumps(metrics, indent=2), encoding="ascii")
        progress_path = Path(args.output) / "progress.json"
        final_payload = reporter.handle({"stage": "complete", **metrics})
        progress_path.write_text(json.dumps(final_payload, indent=2), encoding="ascii")
    tracker.update_summary(metrics)
    tracker.finish(exit_code=0, summary=metrics)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
