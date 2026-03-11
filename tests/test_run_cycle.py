import json
from dataclasses import replace
from pathlib import Path

from hex6.config import load_config
from hex6.train.run_cycle import evaluate_candidate_promotion, write_cycle_root_summary


def test_evaluate_candidate_promotion_auto_promotes_without_incumbent(tmp_path: Path) -> None:
    config = load_config("configs/fast.toml")

    promotion = evaluate_candidate_promotion(
        candidate_checkpoint="candidate.pt",
        incumbent_checkpoint=None,
        config_path="configs/fast.toml",
        config=config,
        output_dir=tmp_path,
    )

    assert promotion["evaluated"] is False
    assert promotion["promoted"] is True
    assert promotion["reason"] == "no_incumbent"


def test_evaluate_candidate_promotion_uses_score_delta_threshold(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = load_config("configs/fast.toml")
    config = replace(
        config,
        evaluation=replace(
            config.evaluation,
            promotion_games_per_match=12,
            promotion_include_baseline=True,
            promotion_require_candidate_rank_one=True,
        ),
    )

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "hex6.train.run_cycle.build_checkpoint_participant",
        lambda checkpoint_path, **_kwargs: type(
            "Participant",
            (),
            {
                "name": "candidate" if "candidate" in str(checkpoint_path) else "incumbent",
                "kind": "guided_mcts",
                "agent": object(),
                "checkpoint_path": str(checkpoint_path),
                "config_path": "configs/fast.toml",
            },
        )(),
    )
    monkeypatch.setattr(
        "hex6.train.run_cycle.build_baseline_agent",
        lambda: type(
            "BaselineAgent",
            (),
            {
                "name": "baseline",
                "kind": "baseline",
                "choose_turn": object(),
            },
        )(),
    )
    monkeypatch.setattr(
        "hex6.train.run_cycle.run_round_robin_tournament",
        lambda **kwargs: captured.update(kwargs)
        or {
            "participants": [
                {"name": "baseline"},
                {"name": "incumbent"},
                {"name": "candidate"},
            ],
            "games_per_match": kwargs["games_per_match"],
            "opening_suite_size": len(kwargs["opening_suite"]) if kwargs["opening_suite"] else 0,
            "leaderboard": [
                {
                    "name": "candidate",
                    "points": 8.0,
                    "wins": 6,
                    "losses": 2,
                    "draws": 4,
                },
                {
                    "name": "baseline",
                    "points": 6.0,
                    "wins": 4,
                    "losses": 4,
                    "draws": 4,
                },
                {
                    "name": "incumbent",
                    "points": 4.0,
                    "wins": 2,
                    "losses": 6,
                    "draws": 4,
                },
            ],
            "summary_path": str(tmp_path / "promotion_match" / "summary.json"),
            "history_path": str(tmp_path / "history.json"),
        },
    )

    promotion = evaluate_candidate_promotion(
        candidate_checkpoint="candidate.pt",
        incumbent_checkpoint="incumbent.pt",
        config_path="configs/fast.toml",
        config=config,
        output_dir=tmp_path,
    )

    assert promotion["evaluated"] is True
    assert promotion["promoted"] is True
    assert promotion["score_delta"] == 4.0
    assert promotion["promotion_min_score_delta"] == 0.5
    assert promotion["candidate_rank"] == 1
    assert promotion["baseline_rank"] == 2
    assert promotion["participant_count"] == 3
    assert promotion["games_per_match"] == 12
    assert promotion["opening_suite_size"] == 12
    assert len(captured["participants"]) == 3
    assert captured["games_per_match"] == 12


def test_evaluate_candidate_promotion_can_reject_candidate_that_is_not_rank_one(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = load_config("configs/fast.toml")

    monkeypatch.setattr(
        "hex6.train.run_cycle.build_checkpoint_participant",
        lambda checkpoint_path, **_kwargs: type(
            "Participant",
            (),
            {
                "name": "candidate" if "candidate" in str(checkpoint_path) else "incumbent",
                "kind": "guided_mcts",
                "agent": object(),
                "checkpoint_path": str(checkpoint_path),
                "config_path": "configs/fast.toml",
            },
        )(),
    )
    monkeypatch.setattr(
        "hex6.train.run_cycle.build_baseline_agent",
        lambda: type(
            "BaselineAgent",
            (),
            {
                "name": "baseline",
                "kind": "baseline",
                "choose_turn": object(),
            },
        )(),
    )
    monkeypatch.setattr(
        "hex6.train.run_cycle.run_round_robin_tournament",
        lambda **_kwargs: {
            "participants": [
                {"name": "baseline"},
                {"name": "incumbent"},
                {"name": "candidate"},
            ],
            "games_per_match": 12,
            "opening_suite_size": 12,
            "leaderboard": [
                {
                    "name": "baseline",
                    "points": 9.0,
                    "wins": 7,
                    "losses": 1,
                    "draws": 4,
                },
                {
                    "name": "candidate",
                    "points": 8.0,
                    "wins": 6,
                    "losses": 2,
                    "draws": 4,
                },
                {
                    "name": "incumbent",
                    "points": 4.0,
                    "wins": 2,
                    "losses": 6,
                    "draws": 4,
                },
            ],
            "summary_path": str(tmp_path / "promotion_match" / "summary.json"),
            "history_path": str(tmp_path / "history.json"),
        },
    )

    promotion = evaluate_candidate_promotion(
        candidate_checkpoint="candidate.pt",
        incumbent_checkpoint="incumbent.pt",
        config_path="configs/fast.toml",
        config=config,
        output_dir=tmp_path,
    )

    assert promotion["evaluated"] is True
    assert promotion["promoted"] is False
    assert promotion["reason"] == "candidate_not_rank_one"
    assert promotion["candidate_rank"] == 2


def test_write_cycle_root_summary_records_best_checkpoint(tmp_path: Path) -> None:
    write_cycle_root_summary(
        tmp_path,
        [
            {
                "cycle_index": 1,
                "promotion": {"promoted": True},
            },
            {
                "cycle_index": 2,
                "promotion": {"promoted": False},
            },
        ],
        latest_checkpoint="cycle_002.pt",
        best_checkpoint="cycle_001.pt",
    )

    payload = json.loads((tmp_path / "cycle_summary.json").read_text(encoding="ascii"))

    assert payload["latest_checkpoint"] == "cycle_002.pt"
    assert payload["best_checkpoint"] == "cycle_001.pt"
    assert payload["promoted_cycles"] == [1]
