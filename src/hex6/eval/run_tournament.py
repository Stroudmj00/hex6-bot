"""CLI entry point for round-robin tournament evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import traceback

from hex6.config import load_config
from hex6.eval.openings import load_opening_suite
from hex6.eval.tournament import (
    build_participants,
    discover_checkpoints,
    run_round_robin_tournament,
)
from hex6.integration import build_status_publisher


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a round-robin tournament for Hex6 agents.")
    parser.add_argument(
        "--config",
        default="configs/fast.toml",
        help="Base config path used for game/evaluation settings.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/tournament/latest",
        help="Directory where tournament outputs will be written.",
    )
    parser.add_argument(
        "--games-per-match",
        type=int,
        default=4,
        help="Number of games per pair.",
    )
    parser.add_argument(
        "--max-game-plies",
        type=int,
        default=48,
        help="Arena ply cap used inside tournament matches.",
    )
    parser.add_argument(
        "--opening-suite",
        default="configs/experiments/opening_suite.toml",
        help="Optional opening suite TOML path used to reduce draw-heavy symmetric starts.",
    )
    parser.add_argument(
        "--no-opening-suite",
        action="store_true",
        help="Disable opening suite and start games from an empty board.",
    )
    parser.add_argument(
        "--checkpoint-glob",
        default="artifacts/**/bootstrap_model.pt",
        help="Glob pattern used when --checkpoint is omitted.",
    )
    parser.add_argument(
        "--checkpoint",
        action="append",
        default=[],
        help="Explicit checkpoint path (can be passed multiple times).",
    )
    parser.add_argument(
        "--max-checkpoints",
        type=int,
        default=3,
        help="Maximum discovered checkpoints when using --checkpoint-glob.",
    )
    parser.add_argument(
        "--include-baseline",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include heuristic baseline agent.",
    )
    parser.add_argument(
        "--include-random",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include random agent.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=7,
        help="Random seed used for the random agent.",
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

    checkpoints = args.checkpoint or [
        str(path)
        for path in discover_checkpoints(args.checkpoint_glob, max_checkpoints=max(args.max_checkpoints, 0))
    ]
    config = load_config(args.config)
    opening_suite = None
    if not args.no_opening_suite and str(args.opening_suite).strip():
        opening_suite_path = Path(args.opening_suite)
        opening_suite = load_opening_suite(opening_suite_path, config)
    effective_games_per_match = max(args.games_per_match, 1)
    if opening_suite and effective_games_per_match < len(opening_suite):
        effective_games_per_match = len(opening_suite)

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
    participants = build_participants(
        base_config_path=args.config,
        include_baseline=args.include_baseline,
        include_random=args.include_random,
        random_seed=args.random_seed,
        checkpoint_paths=checkpoints,
    )
    if status.enabled:
        status.publish(
            {
                "stage": "starting",
                "config_path": args.config,
                "participant_count": len(participants),
                "checkpoint_count": len(checkpoints),
                "requested_games_per_match": max(args.games_per_match, 1),
                "games_per_match": effective_games_per_match,
                "max_game_plies": max(args.max_game_plies, 1),
                "opening_suite_size": len(opening_suite) if opening_suite else 0,
            }
        )
    try:
        summary = run_round_robin_tournament(
            participants=participants,
            config=config,
            games_per_match=max(args.games_per_match, 1),
            max_game_plies=max(args.max_game_plies, 1),
            output_dir=args.output,
            opening_suite=opening_suite,
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
        raise

    if status.enabled:
        status.publish(
            {
                "stage": "complete",
                "leader": summary["leader"],
                "participant_count": len(summary["participants"]),
                "match_count": len(summary["matches"]),
                "games_per_match": summary["games_per_match"],
                "opening_suite_size": summary["opening_suite_size"],
                "draw_rate": summary["draw_rate"],
                "total_draws": summary["total_draws"],
                "total_draws_by_ply_cap": summary["total_draws_by_ply_cap"],
                "summary_path": summary["summary_path"],
                "history_path": summary["history_path"],
            }
        )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
