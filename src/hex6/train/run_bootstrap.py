"""CLI entry point for bootstrap training."""

from __future__ import annotations

import argparse
import json
import traceback

from hex6.config import load_config
from hex6.integration import build_status_publisher
from hex6.train.bootstrap import train_bootstrap


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
    try:
        metrics = train_bootstrap(
            config,
            output_dir=args.output,
            config_path=args.config,
            progress_callback=status.publish,
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
        raise
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
