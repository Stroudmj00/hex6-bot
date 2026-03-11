"""Run a fixed-board evaluation ablation with runtime and resource tracking."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import time

import torch

from hex6.config import AppConfig, load_config, load_config_with_overrides
from hex6.eval import evaluate_checkpoint_with_tournament_gate
from hex6.train.resource_usage import ResourceMonitor


@dataclass(frozen=True)
class EvalCase:
    name: str
    board_width: int
    board_height: int
    games: int
    opening_suite: str


def _select_device(config: AppConfig) -> torch.device:
    if config.runtime.preferred_device == "cuda" and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _run_case(
    *,
    base_config_path: str | Path,
    checkpoint_path: str | Path,
    output_root: Path,
    case: EvalCase,
) -> dict[str, object]:
    config = load_config_with_overrides(
        base_config_path,
        {
            "evaluation": {
                "arena_games": case.games,
                "board_width_override": case.board_width,
                "board_height_override": case.board_height,
                "post_train_opening_suite": case.opening_suite,
                "post_train_max_game_plies": 0,
                "record_game_history": True,
            }
        },
    )
    case_dir = output_root / case.name
    case_dir.mkdir(parents=True, exist_ok=True)

    monitor = ResourceMonitor(
        enabled=config.runtime.record_resource_usage,
        poll_seconds=config.runtime.resource_poll_seconds,
        device=_select_device(config),
    )
    monitor.start()
    started = time.perf_counter()
    summary = evaluate_checkpoint_with_tournament_gate(
        checkpoint_path=checkpoint_path,
        config=config,
        config_path=base_config_path,
        output_dir=case_dir,
        include_baseline=True,
        include_random=False,
    )
    runtime_seconds = round(time.perf_counter() - started, 3)
    resource_payload = monitor.stop(output_path=case_dir / "resource_usage.json")

    payload = {
        "case": asdict(case),
        "runtime_seconds": runtime_seconds,
        "resource_summary": resource_payload.get("summary", {}),
        "result": summary,
    }
    (case_dir / "run_summary.json").write_text(json.dumps(payload, indent=2), encoding="ascii")
    return payload


def _decision(results: dict[str, dict[str, object]]) -> dict[str, object]:
    promotion_15 = results.get("promotion_15x15")
    promotion_25 = results.get("promotion_25x25")
    if promotion_15 is None or promotion_25 is None:
        return {
            "eligible_for_split_default": False,
            "reason": "missing_promotion_result",
        }

    result_15 = promotion_15["result"]
    result_25 = promotion_25["result"]
    score_drop = round(float(result_15["checkpoint_points"]) - float(result_25["checkpoint_points"]), 3)
    draws_15 = int(result_15["total_draws_by_board_exhausted"])
    draws_25 = int(result_25["total_draws_by_board_exhausted"])
    eligible = (
        draws_25 < draws_15
        and score_drop <= 0.5
    )
    return {
        "eligible_for_split_default": eligible,
        "score_drop_vs_15x15_promotion": score_drop,
        "promotion_board_exhausted_draws_15x15": draws_15,
        "promotion_board_exhausted_draws_25x25": draws_25,
        "recommended_eval_board": 25 if eligible else 15,
        "reason": "promotion_draws_reduced_without_material_score_drop"
        if eligible
        else "promotion_decision_rule_not_met",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the split-board evaluation ablation.")
    parser.add_argument(
        "--config",
        default="configs/local_4h_strongest_v2.toml",
        help="Base training config used for model/search/runtime settings.",
    )
    parser.add_argument(
        "--checkpoint",
        required=True,
        help="Checkpoint under test.",
    )
    parser.add_argument(
        "--output-root",
        default="artifacts/board_eval_ablation",
        help="Directory where ablation outputs are written.",
    )
    parser.add_argument(
        "--minutes",
        type=float,
        default=120.0,
        help="Optional wall-clock budget. Promotion runs are prioritized first.",
    )
    args = parser.parse_args()

    base_config = load_config(args.config)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    cases = [
        EvalCase(
            name="promotion_15x15",
            board_width=15,
            board_height=15,
            games=12,
            opening_suite=base_config.evaluation.promotion_opening_suite,
        ),
        EvalCase(
            name="promotion_25x25",
            board_width=25,
            board_height=25,
            games=12,
            opening_suite=base_config.evaluation.promotion_opening_suite,
        ),
        EvalCase(
            name="standard_15x15",
            board_width=15,
            board_height=15,
            games=6,
            opening_suite=base_config.evaluation.post_train_opening_suite,
        ),
        EvalCase(
            name="standard_25x25",
            board_width=25,
            board_height=25,
            games=6,
            opening_suite=base_config.evaluation.post_train_opening_suite,
        ),
    ]

    results: dict[str, dict[str, object]] = {}
    started = time.perf_counter()
    budget_seconds = max(args.minutes, 0.0) * 60.0
    skipped: list[str] = []
    for case in cases:
        elapsed = time.perf_counter() - started
        if budget_seconds > 0 and elapsed >= budget_seconds:
            skipped.append(case.name)
            continue
        results[case.name] = _run_case(
            base_config_path=args.config,
            checkpoint_path=args.checkpoint,
            output_root=output_root,
            case=case,
        )

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_config_path": str(Path(args.config).resolve()),
        "checkpoint_path": str(Path(args.checkpoint).resolve()),
        "requested_budget_minutes": args.minutes,
        "completed_cases": list(results),
        "skipped_cases": skipped,
        "decision": _decision(results),
        "results": results,
    }
    (output_root / "summary.json").write_text(json.dumps(payload, indent=2), encoding="ascii")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
