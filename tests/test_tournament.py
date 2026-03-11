from dataclasses import replace
from pathlib import Path
import os
import time

import pytest
import torch

from hex6.config import load_config
from hex6.eval.arena import AgentSpec, build_evaluation_config
from hex6.eval import evaluate_checkpoint_with_tournament_gate
from hex6.eval.openings import OpeningScenario
from hex6.eval.tournament import (
    build_checkpoint_participant,
    build_participants,
    discover_checkpoints,
    resolve_path_relative_to_config,
    run_round_robin_tournament,
)
from hex6.game import GameState
from hex6.nn import HexPolicyValueNet


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


def test_discover_checkpoints_zero_returns_none(tmp_path: Path) -> None:
    checkpoint = tmp_path / "one" / "bootstrap_model.pt"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"x")

    found = discover_checkpoints(str(tmp_path / "**" / "bootstrap_model.pt"), max_checkpoints=0)
    assert found == []


def test_round_robin_tournament_writes_summary(tmp_path: Path) -> None:
    config = load_config("configs/fast.toml")
    config = replace(
        config,
        evaluation=replace(config.evaluation, max_game_plies=8, record_game_history=False),
    )
    participants = build_participants(
        agent_config=config,
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
    assert summary["board_width"] == config.game.board_width
    assert summary["board_height"] == config.game.board_height
    assert "draw_rate" in summary
    assert "total_draws_by_ply_cap" in summary
    assert (tmp_path / "tournament" / "summary.json").exists()


def test_round_robin_tournament_reports_progress(tmp_path: Path) -> None:
    config = load_config("configs/fast.toml")
    config = replace(
        config,
        evaluation=replace(config.evaluation, max_game_plies=8, record_game_history=False),
    )
    participants = build_participants(
        agent_config=config,
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


def test_round_robin_tournament_auto_expands_games_to_cover_opening_suite(tmp_path: Path) -> None:
    config = load_config("configs/fast.toml")
    config = replace(
        config,
        evaluation=replace(config.evaluation, max_game_plies=8, record_game_history=False),
    )
    participants = build_participants(
        agent_config=config,
        base_config_path="configs/fast.toml",
        include_baseline=True,
        include_random=True,
        random_seed=11,
        checkpoint_paths=[],
    )

    opening_state = GameState.initial(config.game).apply_placement((0, 0), config.game)
    opening_suite = [
        OpeningScenario(name="open_a", description="seed a", placements=((0, 0),), state=opening_state),
        OpeningScenario(name="open_b", description="seed b", placements=((0, 0),), state=opening_state),
    ]

    summary = run_round_robin_tournament(
        participants=participants,
        config=config,
        games_per_match=1,
        max_game_plies=8,
        output_dir=tmp_path / "tournament_openings",
        opening_suite=opening_suite,
    )

    assert summary["requested_games_per_match"] == 1
    assert summary["games_per_match"] == 2
    assert summary["opening_suite_size"] == 2


def test_resolve_path_relative_to_config_accepts_repo_relative_opening_suite() -> None:
    resolved = resolve_path_relative_to_config("configs/fast.toml", "configs/experiments/opening_suite.toml")

    assert resolved == Path("configs/experiments/opening_suite.toml").resolve()


def test_resolve_path_relative_to_config_rejects_ambiguous_relative_suite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "nested" / "fast.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(Path("configs/fast.toml").read_text(encoding="ascii"), encoding="ascii")
    (config_path.parent / "opening_suite.toml").write_text("", encoding="ascii")
    (tmp_path / "opening_suite.toml").write_text("", encoding="ascii")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="ambiguous relative path"):
        resolve_path_relative_to_config(config_path, "opening_suite.toml")


def test_resolve_path_relative_to_config_rejects_missing_suite_path(tmp_path: Path) -> None:
    config_path = tmp_path / "nested" / "fast.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(Path("configs/fast.toml").read_text(encoding="ascii"), encoding="ascii")

    with pytest.raises(ValueError, match="could not resolve path"):
        resolve_path_relative_to_config(config_path, "missing_suite.toml")


def test_evaluate_checkpoint_with_tournament_gate_writes_compact_summary(tmp_path: Path) -> None:
    config = load_config("configs/fast.toml")
    config = replace(
        config,
        evaluation=replace(
            config.evaluation,
            arena_games=2,
            post_train_max_game_plies=8,
            post_train_opening_suite="",
            record_game_history=False,
        ),
    )
    model = HexPolicyValueNet(
        input_channels=6,
        channels=config.model.channels,
        blocks=config.model.blocks,
    )
    checkpoint_path = tmp_path / "gate" / "bootstrap_model.pt"
    checkpoint_path.parent.mkdir(parents=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "config_path": "configs/fast.toml",
            "history": [],
        },
        checkpoint_path,
    )

    summary = evaluate_checkpoint_with_tournament_gate(
        checkpoint_path=checkpoint_path,
        config=config,
        config_path="configs/fast.toml",
        output_dir=tmp_path / "gate_eval",
    )

    assert summary["kind"] == "tournament"
    assert summary["participant_count"] == 2
    assert summary["board_width"] == config.game.board_width
    assert summary["board_height"] == config.game.board_height
    assert summary["checkpoint_rank"] in {1, 2}
    assert Path(summary["summary_path"]).exists()


def test_evaluate_checkpoint_with_tournament_gate_resolves_opening_suite_relative_to_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config("configs/fast.toml")
    config = replace(
        config,
        evaluation=replace(
            config.evaluation,
            arena_games=1,
            post_train_max_game_plies=8,
            post_train_opening_suite="opening_suite.toml",
            record_game_history=False,
        ),
    )
    model = HexPolicyValueNet(
        input_channels=6,
        channels=config.model.channels,
        blocks=config.model.blocks,
    )
    checkpoint_path = tmp_path / "gate" / "bootstrap_model.pt"
    checkpoint_path.parent.mkdir(parents=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "config_path": "configs/fast.toml",
            "history": [],
        },
        checkpoint_path,
    )
    config_path = tmp_path / "nested" / "gate_config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(Path("configs/fast.toml").read_text(encoding="ascii"), encoding="ascii")
    (config_path.parent / "opening_suite.toml").write_text(
        "\n".join(
            [
                "[[scenarios]]",
                'name = "single_seed"',
                'description = "one seeded start"',
                "placements = [[0, 0]]",
                'expected_to_play = "o"',
                "expected_placements_remaining = 2",
                "",
            ]
        ),
        encoding="ascii",
    )
    monkeypatch.chdir(tmp_path.parent)

    summary = evaluate_checkpoint_with_tournament_gate(
        checkpoint_path=checkpoint_path,
        config=config,
        config_path=config_path,
        output_dir=tmp_path / "gate_eval_relative",
    )

    assert summary["opening_suite_size"] == 1


def test_build_evaluation_config_applies_eval_board_override() -> None:
    config = load_config("configs/fast.toml")
    overridden = replace(
        config,
        evaluation=replace(
            config.evaluation,
            board_width_override=25,
            board_height_override=25,
        ),
    )

    eval_config = build_evaluation_config(overridden)

    assert overridden.game.board_width == 15
    assert overridden.game.board_height == 15
    assert eval_config.game.board_width == 25
    assert eval_config.game.board_height == 25


def test_build_checkpoint_participant_uses_eval_agent_config_for_search(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config("configs/fast.toml")
    eval_config = replace(
        config,
        game=replace(config.game, board_width=25, board_height=25),
    )
    model = HexPolicyValueNet(
        input_channels=6,
        channels=config.model.channels,
        blocks=config.model.blocks,
    )
    checkpoint_path = tmp_path / "checkpoint.pt"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "config_path": "configs/fast.toml",
            "history": [],
        },
        checkpoint_path,
    )

    captured: dict[str, object] = {}

    def fake_build_checkpoint_agent(path, build_config):
        captured["path"] = str(path)
        captured["board_width"] = build_config.game.board_width
        captured["board_height"] = build_config.game.board_height
        return AgentSpec(name="fake", kind="guided_mcts", choose_turn=lambda state, arena_config: object())

    monkeypatch.setattr("hex6.eval.tournament.build_checkpoint_agent", fake_build_checkpoint_agent)

    participant = build_checkpoint_participant(
        checkpoint_path,
        agent_config=eval_config,
        fallback_config_path="configs/fast.toml",
        display_name="checkpoint_eval",
    )

    assert participant.name == "checkpoint_eval"
    assert captured["board_width"] == 25
    assert captured["board_height"] == 25
    assert participant.config_path == str(Path("configs/fast.toml").resolve())
