"""CLI entry point for arena evaluation."""

from __future__ import annotations

import argparse
import json

from hex6.config import load_config
from hex6.eval.arena import evaluate_checkpoint_against_baseline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run checkpoint arena evaluation for Hex6.")
    parser.add_argument(
        "--config",
        default="configs/colab.toml",
        help="Path to the TOML config file.",
    )
    parser.add_argument(
        "--checkpoint",
        required=True,
        help="Path to the checkpoint file.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/arena",
        help="Directory where arena results will be written.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    summary = evaluate_checkpoint_against_baseline(
        checkpoint_path=args.checkpoint,
        config=config,
        output_dir=args.output,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
