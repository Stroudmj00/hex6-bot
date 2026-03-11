from dataclasses import replace
from pathlib import Path

import pytest
import torch

from hex6.config import load_config, load_config_with_overrides
from hex6.eval import AgentSpec, build_random_agent, run_arena
from hex6.eval.arena import build_evaluation_config
from hex6.game import GameState, IllegalMoveError
from hex6.nn import HexPolicyValueNet
from hex6.search import BaselineTurnSearch, ModelGuidedTurnSearch
from hex6.eval.arena import play_game


def test_model_guided_search_returns_legal_turn(tmp_path: Path) -> None:
    config = load_config("configs/fast.toml")
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

    search = ModelGuidedTurnSearch.from_checkpoint(checkpoint_path, config, device=torch.device("cpu"))
    state = GameState.initial(config.game).apply_placement((0, 0), config.game)
    turn = search.choose_turn(state, config)

    assert len(turn.cells) == 2
    assert all(state.is_empty(cell) for cell in turn.cells)


def test_model_guided_search_supports_partial_checkpoint_warm_start(tmp_path: Path) -> None:
    source_config = load_config_with_overrides("configs/fast.toml", {"model": {"blocks": 2}})
    target_config = load_config_with_overrides("configs/fast.toml", {"model": {"blocks": 3}})
    model = HexPolicyValueNet(
        input_channels=6,
        channels=source_config.model.channels,
        blocks=source_config.model.blocks,
    )
    checkpoint_path = tmp_path / "partial_checkpoint.pt"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "config_path": "configs/fast.toml",
            "history": [],
        },
        checkpoint_path,
    )

    search = ModelGuidedTurnSearch.from_checkpoint(checkpoint_path, target_config, device=torch.device("cpu"))
    state = GameState.initial(target_config.game).apply_placement((0, 0), target_config.game)
    turn = search.choose_turn(state, target_config)

    assert len(turn.cells) == 2
    assert all(state.is_empty(cell) for cell in turn.cells)


def test_run_arena_tracks_results_and_elo() -> None:
    config = load_config("configs/fast.toml")
    config = replace(
        config,
        evaluation=replace(config.evaluation, max_game_plies=16, record_game_history=False),
    )

    search_a = BaselineTurnSearch()
    search_b = BaselineTurnSearch()
    summary = run_arena(
        agent_a=AgentSpec(name="baseline-a", kind="heuristic", choose_turn=search_a.choose_turn),
        agent_b=AgentSpec(name="baseline-b", kind="heuristic", choose_turn=search_b.choose_turn),
        config=config,
        games=2,
    )

    assert summary["games"] == 2
    assert summary["board_width"] == config.game.board_width
    assert summary["board_height"] == config.game.board_height
    assert summary["wins_a"] + summary["wins_b"] + summary["draws"] == 2
    assert "final_elo_a" in summary
    assert "draws_by_ply_cap" in summary
    assert "avg_plies" in summary
    assert "game_history" not in summary


def test_run_arena_game_history_includes_fill_and_edge_metrics() -> None:
    config = load_config("configs/fast.toml")

    summary = run_arena(
        agent_a=AgentSpec(name="baseline-a", kind="heuristic", choose_turn=BaselineTurnSearch().choose_turn),
        agent_b=AgentSpec(name="baseline-b", kind="heuristic", choose_turn=BaselineTurnSearch().choose_turn),
        config=config,
        games=1,
    )

    game = summary["game_history"][0]
    assert "occupied_count" in game
    assert "board_fill_fraction" in game
    assert "occupied_span_q" in game
    assert "occupied_span_r" in game
    assert "winning_line_edge_distance" in game


def test_random_agent_returns_legal_turn() -> None:
    config = load_config("configs/fast.toml")
    agent = build_random_agent(seed=3, candidate_width=8)
    state = GameState.initial(config.game).apply_placement((0, 0), config.game)

    turn = agent.choose_turn(state, config)

    assert len(turn.cells) == state.placements_remaining
    assert len(set(turn.cells)) == len(turn.cells)
    assert all(state.is_empty(cell) for cell in turn.cells)


def test_play_game_uses_board_exhausted_draw_on_tiny_bounded_board() -> None:
    config = load_config_with_overrides(
        "configs/fast.toml",
        {
            "game": {
                "board_width": 1,
                "board_height": 3,
            },
            "evaluation": {
                "max_game_plies": 0,
            },
        },
    )
    def fill_remaining_cells(state, config):
        bounds = config.game.bounds()
        assert bounds is not None
        min_q, max_q, min_r, max_r = bounds
        cells = []
        for q in range(min_q, max_q + 1):
            for r in range(min_r, max_r + 1):
                cell = (q, r)
                if state.is_empty(cell):
                    cells.append(cell)
                if len(cells) == state.placements_remaining:
                    return type("Turn", (), {"cells": tuple(cells)})()
        raise AssertionError("expected enough legal cells to complete the turn")

    winner, plies, termination, final_state = play_game(
        {
            "x": AgentSpec(name="x", kind="scripted", choose_turn=fill_remaining_cells),
            "o": AgentSpec(name="o", kind="scripted", choose_turn=fill_remaining_cells),
        },
        config=config,
    )

    assert winner is None
    assert plies == 3
    assert termination == "board_exhausted"
    assert final_state.draw_reason == "board_exhausted"


def test_play_game_rejects_turn_with_too_few_cells() -> None:
    config = load_config("configs/fast.toml")
    state = GameState.initial(config.game).apply_placement((0, 0), config.game)
    bad_turn = type("BadTurn", (), {"cells": ((1, 0),)})
    agent = AgentSpec(name="bad-too-few", kind="bad", choose_turn=lambda _state, _config: bad_turn())

    with pytest.raises(IllegalMoveError, match="expected 2 placements"):
        play_game({"x": agent, "o": agent}, config=config, starting_state=state)


def test_play_game_rejects_turn_with_too_many_cells() -> None:
    config = load_config("configs/fast.toml")
    state = GameState.initial(config.game).apply_placement((0, 0), config.game)
    bad_turn = type("BadTurn", (), {"cells": ((1, 0), (2, 0), (3, 0))})
    agent = AgentSpec(
        name="bad-too-many",
        kind="bad",
        choose_turn=lambda _state, _config: bad_turn(),
    )

    with pytest.raises(IllegalMoveError, match="expected 2 placements"):
        play_game({"x": agent, "o": agent}, config=config, starting_state=state)


def test_build_evaluation_config_keeps_training_board_unchanged() -> None:
    config = load_config_with_overrides(
        "configs/fast.toml",
        {
            "evaluation": {
                "board_width_override": 25,
                "board_height_override": 25,
            }
        },
    )

    eval_config = build_evaluation_config(config)

    assert config.game.board_width == 15
    assert config.game.board_height == 15
    assert eval_config.game.board_width == 25
    assert eval_config.game.board_height == 25
