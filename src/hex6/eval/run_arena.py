"""CLI entry point for arena evaluation."""

from __future__ import annotations

import argparse
import json

from hex6.config import load_config
from hex6.eval.arena import evaluate_checkpoint_against_opponent


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
    parser.add_argument(
        "--opponent",
        choices=["baseline", "random", "checkpoint"],
        default="baseline",
        help="Opponent type for agent_b.",
    )
    parser.add_argument(
        "--opponent-checkpoint",
        default="",
        help="Required only when --opponent checkpoint.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=7,
        help="Seed used when --opponent random.",
    )
    parser.add_argument(
        "--random-candidate-width",
        type=int,
        default=24,
        help="Candidate pool width for random policy.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    summary = evaluate_checkpoint_against_opponent(
        checkpoint_path=args.checkpoint,
        config=config,
        output_dir=args.output,
        opponent=args.opponent,
        opponent_checkpoint_path=args.opponent_checkpoint or None,
        random_seed=args.random_seed,
        random_candidate_width=max(args.random_candidate_width, 1),
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
