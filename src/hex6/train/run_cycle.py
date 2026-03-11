"""Run repeated bootstrap/evaluation cycles for a time budget or cycle count."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import traceback

from hex6.config import load_config
from hex6.eval.arena import build_evaluation_config
from hex6.eval import (
    append_elo_history,
    build_baseline_agent,
    evaluate_checkpoint_against_baseline,
    evaluate_checkpoint_with_tournament_gate,
)
from hex6.eval.openings import load_opening_suite
from hex6.eval.tournament import (
    TournamentParticipant,
    build_checkpoint_participant,
    resolve_path_relative_to_config,
    run_round_robin_tournament,
)
from hex6.integration import build_status_publisher
from hex6.train.bootstrap import train_bootstrap
from hex6.train.progress_reporting import CycleProgressReporter, build_cycle_phase_callback
from hex6.train.tracking import build_experiment_tracker


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
    if config.evaluation.post_train_eval not in {"arena", "tournament"}:
        raise ValueError(f"unsupported evaluation.post_train_eval: {config.evaluation.post_train_eval}")
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
    tracker = build_experiment_tracker(
        config,
        config_path=args.config,
        output_dir=output_root,
        run_id=status.run_id,
        job_type="cycle",
    )
    tracker.log(
        {
            "stage": "starting",
            "run_id": status.run_id,
            "status_backend": status.backend,
            "status_target": status.target_description(),
            "minutes": args.minutes,
            "cycles": args.cycles,
        }
    )

    start_time = time.monotonic()
    time_budget_seconds = None if args.minutes is None else args.minutes * 60.0
    best_checkpoint = args.start_checkpoint
    latest_checkpoint = args.start_checkpoint
    cycle_index = 1
    summaries: list[dict[str, object]] = []
    replay_buffer_path = output_root / "replay_buffer.pkl"
    cycle_reporter = CycleProgressReporter(
        publish=status.publish if status.enabled else None,
        max_cycles=args.cycles,
        time_budget_seconds=time_budget_seconds,
        started_monotonic=start_time,
    )

    try:
        while should_continue(cycle_index, args.cycles, start_time, time_budget_seconds):
            cycle_dir = output_root / f"cycle_{cycle_index:03d}"
            cycle_dir.mkdir(parents=True, exist_ok=True)
            training_callback = build_cycle_phase_callback(
                cycle_reporter,
                cycle_index=cycle_index,
                phase="training",
            )
            metrics = train_bootstrap(
                config,
                output_dir=cycle_dir,
                config_path=args.config,
                progress_callback=training_callback,
                final_stage="cycle_training_complete",
                init_checkpoint_path=best_checkpoint,
                replay_buffer_path=replay_buffer_path,
            )
            candidate_checkpoint = str(metrics["checkpoint"])
            cycle_summary: dict[str, object] = {
                "cycle_index": cycle_index,
                "started_at": utc_now(),
                "metrics": metrics,
                "init_checkpoint": best_checkpoint,
                "candidate_checkpoint": candidate_checkpoint,
                "best_checkpoint_before": best_checkpoint,
            }
            if config.evaluation.arena_games > 0:
                if config.evaluation.post_train_eval == "tournament":
                    post_train = evaluate_checkpoint_with_tournament_gate(
                        checkpoint_path=candidate_checkpoint,
                        config=config,
                        config_path=args.config,
                        output_dir=cycle_dir,
                        extra_checkpoint_paths=[best_checkpoint] if best_checkpoint else (),
                        include_baseline=True,
                        include_random=False,
                        progress_callback=build_cycle_phase_callback(
                            cycle_reporter,
                            cycle_index=cycle_index,
                            phase="post_train_evaluation",
                        ),
                    )
                else:
                    arena = evaluate_checkpoint_against_baseline(
                        checkpoint_path=metrics["checkpoint"],
                        config=config,
                        output_dir=cycle_dir,
                        progress_callback=build_cycle_phase_callback(
                            cycle_reporter,
                            cycle_index=cycle_index,
                            phase="post_train_evaluation",
                        ),
                    )
                    cycle_summary["arena"] = arena
                    append_elo_history(output_root / "elo_history.json", arena)
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
                cycle_summary["post_train_evaluation"] = post_train

            promotion = evaluate_candidate_promotion(
                candidate_checkpoint=candidate_checkpoint,
                incumbent_checkpoint=best_checkpoint,
                config_path=args.config,
                config=config,
                output_dir=cycle_dir,
                progress_callback=build_cycle_phase_callback(
                    cycle_reporter,
                    cycle_index=cycle_index,
                    phase="promotion",
                ),
            )
            cycle_summary["promotion"] = promotion
            promoted = bool(promotion["promoted"])
            if promoted or best_checkpoint is None:
                best_checkpoint = candidate_checkpoint
            latest_checkpoint = candidate_checkpoint
            cycle_summary["latest_checkpoint"] = latest_checkpoint
            cycle_summary["best_checkpoint_after"] = best_checkpoint
            summaries.append(cycle_summary)
            tracker.log(
                {
                    "cycle_index": cycle_index,
                    "metrics": metrics,
                    "post_train_evaluation": cycle_summary.get("post_train_evaluation"),
                    "promotion": promotion,
                    "latest_checkpoint": latest_checkpoint,
                    "best_checkpoint_after": best_checkpoint,
                },
                step=cycle_index,
            )
            tracker.update_summary(
                {
                    "latest_checkpoint": latest_checkpoint,
                    "best_checkpoint": best_checkpoint,
                    "cycles_completed": len(summaries),
                }
            )
            write_cycle_root_summary(
                output_root,
                summaries,
                latest_checkpoint=latest_checkpoint,
                best_checkpoint=best_checkpoint,
            )
            payload = {
                "stage": "cycle_complete",
                "cycle_index": cycle_index,
                "cycles_completed": len(summaries),
                "latest_checkpoint": latest_checkpoint,
                "best_checkpoint": best_checkpoint,
                "summary_path": str(output_root / "cycle_summary.json"),
            }
            if "post_train_evaluation" in cycle_summary:
                payload["latest_eval_kind"] = cycle_summary["post_train_evaluation"]["kind"]
                payload["latest_checkpoint_rank"] = cycle_summary["post_train_evaluation"]["checkpoint_rank"]
                payload["latest_win_rate"] = cycle_summary["post_train_evaluation"]["checkpoint_win_rate"]
                payload["latest_draw_rate"] = cycle_summary["post_train_evaluation"]["draw_rate"]
            payload["promoted"] = promoted
            payload["best_checkpoint_changed"] = promoted or cycle_index == 1
            cycle_reporter.handle(payload)
            cycle_index += 1
    except Exception as exc:
        cycle_reporter.handle(
            {
                "stage": "failed",
                "cycle_index": cycle_index,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
        tracker.finish(
            exit_code=1,
            summary={
                "stage": "failed",
                "cycle_index": cycle_index,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        raise

    final_summary = {
        "cycles_completed": len(summaries),
        "latest_checkpoint": latest_checkpoint,
        "best_checkpoint": best_checkpoint,
        "summary_path": str(output_root / "cycle_summary.json"),
        "elo_history_path": str(output_root / "elo_history.json"),
    }
    if summaries and "post_train_evaluation" in summaries[-1]:
        final_summary["latest_eval_kind"] = summaries[-1]["post_train_evaluation"]["kind"]
        final_summary["latest_checkpoint_rank"] = summaries[-1]["post_train_evaluation"]["checkpoint_rank"]
        final_summary["latest_win_rate"] = summaries[-1]["post_train_evaluation"]["checkpoint_win_rate"]
    cycle_reporter.handle({"stage": "complete", **final_summary, "cycle_index": max(len(summaries), 1)})
    tracker.update_summary(final_summary)
    tracker.finish(exit_code=0, summary=final_summary)
    print(json.dumps(final_summary, indent=2))


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
    *,
    latest_checkpoint: str | None,
    best_checkpoint: str | None,
) -> None:
    promoted_cycles = [
        cycle["cycle_index"]
        for cycle in summaries
        if isinstance(cycle.get("promotion"), dict) and cycle["promotion"].get("promoted")
    ]
    payload = {
        "generated_at": utc_now(),
        "cycles_completed": len(summaries),
        "latest_checkpoint": latest_checkpoint,
        "best_checkpoint": best_checkpoint,
        "promoted_cycles": promoted_cycles,
        "cycles": summaries,
    }
    (output_root / "cycle_summary.json").write_text(json.dumps(payload, indent=2), encoding="ascii")


def evaluate_candidate_promotion(
    *,
    candidate_checkpoint: str,
    incumbent_checkpoint: str | None,
    config_path: str,
    config,
    output_dir: Path,
    progress_callback=None,
) -> dict[str, object]:
    if incumbent_checkpoint is None:
        return {
            "evaluated": False,
            "promoted": True,
            "reason": "no_incumbent",
            "candidate_checkpoint": candidate_checkpoint,
            "incumbent_checkpoint": None,
            "summary_path": None,
        }

    eval_config = build_evaluation_config(config)
    opening_suite = None
    opening_suite_path = eval_config.evaluation.promotion_opening_suite.strip() or eval_config.evaluation.post_train_opening_suite
    if opening_suite_path.strip():
        opening_suite = load_opening_suite(
            resolve_path_relative_to_config(config_path, opening_suite_path),
            eval_config,
        )
    participants: list[TournamentParticipant] = []
    if eval_config.evaluation.promotion_include_baseline:
        baseline = build_baseline_agent()
        participants.append(
            TournamentParticipant(
                name=baseline.name,
                kind=baseline.kind,
                agent=baseline,
            )
        )
    participants.extend(
        (
            build_checkpoint_participant(
                incumbent_checkpoint,
                agent_config=eval_config,
                fallback_config_path=config_path,
                display_name="incumbent",
            ),
            build_checkpoint_participant(
                candidate_checkpoint,
                agent_config=eval_config,
                fallback_config_path=config_path,
                display_name="candidate",
            ),
        )
    )
    games_per_match = eval_config.evaluation.promotion_games_per_match
    if games_per_match <= 0:
        games_per_match = max(eval_config.evaluation.arena_games, 1)
    summary = run_round_robin_tournament(
        participants=tuple(participants),
        config=eval_config,
        games_per_match=games_per_match,
        output_dir=output_dir / "promotion_match",
        max_game_plies=eval_config.evaluation.post_train_max_game_plies,
        opening_suite=opening_suite,
        progress_callback=progress_callback,
    )
    leaderboard = {entry["name"]: entry for entry in summary["leaderboard"]}
    ranks = {
        str(entry["name"]): index
        for index, entry in enumerate(summary["leaderboard"], start=1)
    }
    incumbent_entry = leaderboard["incumbent"]
    candidate_entry = leaderboard["candidate"]
    baseline_entry = leaderboard.get("baseline")
    candidate_score = float(candidate_entry["points"])
    incumbent_score = float(incumbent_entry["points"])
    score_delta = round(candidate_score - incumbent_score, 3)
    promoted = score_delta >= eval_config.evaluation.promotion_min_score_delta
    reason = "score_delta_met" if promoted else "score_delta_not_met"
    if promoted and eval_config.evaluation.promotion_require_candidate_rank_one and ranks["candidate"] != 1:
        promoted = False
        reason = "candidate_not_rank_one"
    return {
        "evaluated": True,
        "promoted": promoted,
        "reason": reason,
        "candidate_checkpoint": candidate_checkpoint,
        "incumbent_checkpoint": incumbent_checkpoint,
        "participant_count": len(summary["participants"]),
        "games_per_match": summary["games_per_match"],
        "board_width": summary.get("board_width"),
        "board_height": summary.get("board_height"),
        "opening_suite_size": summary["opening_suite_size"],
        "candidate_rank": ranks["candidate"],
        "incumbent_rank": ranks["incumbent"],
        "baseline_rank": ranks.get("baseline"),
        "candidate_points": candidate_score,
        "incumbent_points": incumbent_score,
        "baseline_points": baseline_entry["points"] if baseline_entry is not None else None,
        "candidate_wins": candidate_entry["wins"],
        "candidate_losses": candidate_entry["losses"],
        "candidate_draws": candidate_entry["draws"],
        "incumbent_wins": incumbent_entry["wins"],
        "incumbent_losses": incumbent_entry["losses"],
        "incumbent_draws": incumbent_entry["draws"],
        "baseline_wins": baseline_entry["wins"] if baseline_entry is not None else None,
        "baseline_losses": baseline_entry["losses"] if baseline_entry is not None else None,
        "baseline_draws": baseline_entry["draws"] if baseline_entry is not None else None,
        "score_delta": score_delta,
        "promotion_min_score_delta": eval_config.evaluation.promotion_min_score_delta,
        "summary_path": summary["summary_path"],
        "history_path": summary["history_path"],
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    main()
