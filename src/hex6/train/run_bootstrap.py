"""CLI entry point for bootstrap training."""

from __future__ import annotations

import argparse
import json

from hex6.config import load_config
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
    args = parser.parse_args()

    config = load_config(args.config)
    metrics = train_bootstrap(config, output_dir=args.output, config_path=args.config)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
