"""CLI entry point for the resumable Colab engine ladder."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import traceback

from hex6.config import load_config
from hex6.eval.ladder import run_ladder
from hex6.integration import build_status_publisher
from hex6.train.tracking import build_experiment_tracker


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the resumable Hex6 engine ladder.")
    parser.add_argument(
        "--config",
        default="configs/colab_ladder.toml",
        help="Base config path used for ladder settings and evaluation defaults.",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="Optional ladder manifest override. Defaults to ladder.submissions_manifest_path.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output directory override. Defaults to ladder.output_root.",
    )
    parser.add_argument(
        "--state",
        default=None,
        help="Optional state path override. Defaults to ladder.state_path.",
    )
    parser.add_argument(
        "--ledger",
        default=None,
        help="Optional ledger path override. Defaults to ladder.ledger_path.",
    )
    parser.add_argument(
        "--max-submissions",
        type=int,
        default=None,
        help="Optional cap on how many pending submissions to process in this run.",
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Resume from the existing ladder state when present.",
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
    manifest_path = _resolve_output_path(args.config, args.manifest or config.ladder.submissions_manifest_path)
    output_dir = _resolve_output_path(args.config, args.output or config.ladder.output_root)
    state_path = _resolve_output_path(args.config, args.state or config.ladder.state_path)
    ledger_path = _resolve_output_path(args.config, args.ledger or config.ladder.ledger_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    status = build_status_publisher(
        config,
        config_path=args.config,
        output_dir=str(output_dir),
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
        output_dir=output_dir,
        run_id=status.run_id,
        job_type="ladder",
    )
    tracker.log(
        {
            "stage": "starting",
            "manifest_path": str(manifest_path),
            "output_dir": str(output_dir),
            "state_path": str(state_path),
            "ledger_path": str(ledger_path),
            "resume": args.resume,
            "max_submissions": args.max_submissions,
        }
    )
    if status.enabled:
        status.publish(
            {
                "stage": "starting",
                "manifest_path": str(manifest_path),
                "output_dir": str(output_dir),
                "state_path": str(state_path),
                "ledger_path": str(ledger_path),
                "resume": args.resume,
                "max_submissions": args.max_submissions,
            }
        )

    try:
        summary = run_ladder(
            config=config,
            config_path=args.config,
            manifest_path=manifest_path,
            output_dir=output_dir,
            state_path=state_path,
            ledger_path=ledger_path,
            resume=args.resume,
            max_submissions=args.max_submissions,
            progress_callback=status.publish if status.enabled else None,
        )
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
        tracker.finish(
            exit_code=1,
            summary={
                "stage": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        raise

    tracker.update_summary(summary)
    tracker.finish(exit_code=0, summary=summary)
    if status.enabled:
        status.publish(
            {
                "stage": "complete",
                "champion_submission_id": summary["champion"]["submission_id"],
                "processed_submissions": len(summary["processed_submission_ids"]),
                "remaining_submissions": len(summary["remaining_submission_ids"]),
                "state_path": summary["state_path"],
                "ledger_path": summary["ledger_path"],
                "summary_path": summary["summary_path"],
            }
        )
    print(json.dumps(summary, indent=2))


def _resolve_output_path(config_path: str | Path, raw_path: str | Path) -> Path:
    del config_path
    path = Path(raw_path)
    if path.is_absolute():
        return path.resolve()
    return (Path.cwd() / path).resolve()


if __name__ == "__main__":
    main()
