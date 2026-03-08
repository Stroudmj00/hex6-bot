from dataclasses import replace
from pathlib import Path
import os
import time

from hex6.config import load_config
from hex6.eval.tournament import build_participants, discover_checkpoints, run_round_robin_tournament


def test_discover_checkpoints_orders_by_mtime(tmp_path: Path) -> None:
    older = tmp_path / "older" / "bootstrap_model.pt"
    newer = tmp_path / "newer" / "bootstrap_model.pt"
    older.parent.mkdir(parents=True)
    newer.parent.mkdir(parents=True)
    older.write_bytes(b"old")
    time.sleep(0.01)
    newer.write_bytes(b"new")

    now = time.time()
    os.utime(older, (now - 5, now - 5))
    os.utime(newer, (now, now))

    found = discover_checkpoints(str(tmp_path / "**" / "bootstrap_model.pt"), max_checkpoints=1)
    assert found == [newer.resolve()]


def test_round_robin_tournament_writes_summary(tmp_path: Path) -> None:
    config = load_config("configs/fast.toml")
    config = replace(
        config,
        evaluation=replace(config.evaluation, max_game_plies=8, record_game_history=False),
    )
    participants = build_participants(
        base_config_path="configs/fast.toml",
        include_baseline=True,
        include_random=True,
        random_seed=5,
        checkpoint_paths=[],
    )

    summary = run_round_robin_tournament(
        participants=participants,
        config=config,
        games_per_match=2,
        max_game_plies=8,
        output_dir=tmp_path / "tournament",
    )

    assert summary["leader"] in {"baseline", "random_seed_5"}
    assert len(summary["participants"]) == 2
    assert len(summary["matches"]) == 1
    assert (tmp_path / "tournament" / "summary.json").exists()


def test_round_robin_tournament_reports_progress(tmp_path: Path) -> None:
    config = load_config("configs/fast.toml")
    config = replace(
        config,
        evaluation=replace(config.evaluation, max_game_plies=8, record_game_history=False),
    )
    participants = build_participants(
        base_config_path="configs/fast.toml",
        include_baseline=True,
        include_random=True,
        random_seed=9,
        checkpoint_paths=[],
    )
    events: list[dict[str, object]] = []

    summary = run_round_robin_tournament(
        participants=participants,
        config=config,
        games_per_match=1,
        max_game_plies=8,
        output_dir=tmp_path / "tournament_progress",
        progress_callback=events.append,
    )

    assert summary["leader"] in {"baseline", "random_seed_9"}
    assert len(events) == 1
    assert events[0]["stage"] == "tournament"
    assert events[0]["completed_matches"] == 1
    assert events[0]["total_matches"] == 1
