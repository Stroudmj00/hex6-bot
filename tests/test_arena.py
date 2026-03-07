from dataclasses import replace
from pathlib import Path

import torch

from hex6.config import load_config
from hex6.eval import AgentSpec, run_arena
from hex6.game import GameState
from hex6.nn import HexPolicyValueNet
from hex6.search import BaselineTurnSearch, ModelGuidedTurnSearch


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
    assert summary["wins_a"] + summary["wins_b"] + summary["draws"] == 2
    assert "final_elo_a" in summary
    assert "game_history" not in summary
