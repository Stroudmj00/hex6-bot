from dataclasses import dataclass
from types import MethodType, SimpleNamespace

import torch

from hex6.config import load_config_with_overrides
from hex6.game import GameState
from hex6.search.baseline import ScoredTurn
from hex6.search.model_guided import ModelGuidedTurnSearch


class DummyModel:
    def eval(self) -> "DummyModel":
        return self


@dataclass
class DummyBaseline:
    def choose_turn(self, state, config):  # pragma: no cover - not used in this test
        raise AssertionError("choose_turn should not be called")

    def enumerate_turns(self, state, config, *, player, first_width, second_width):
        return [
            ScoredTurn(cells=((0, 1), (0, 2)), score=0.0, reply_score=0.0, evaluation_score=0.0, reason="a"),
            ScoredTurn(cells=((0, 1), (1, 2)), score=0.0, reply_score=0.0, evaluation_score=0.0, reason="b"),
        ]

    def apply_cells(self, state, cells, config):
        return state.apply_turn(cells, config.game)

    def evaluate_cached(self, state, config, player):
        return SimpleNamespace(total=0.0)


def test_model_guided_search_uses_second_placement_policy_signal() -> None:
    config = load_config_with_overrides(
        "configs/play.toml",
        {
            "evaluation": {
                "model_policy_weight": 1.0,
                "model_value_weight": 0.0,
                "model_heuristic_weight": 0.0,
            }
        },
    )
    state = GameState.initial(config.game)
    for cell in ((0, 0), (2, 0), (2, 1)):
        state = state.apply_placement(cell, config.game)

    search = ModelGuidedTurnSearch(DummyModel(), device=torch.device("cpu"), baseline=DummyBaseline())

    def fake_policy_scores(self, position, _config, _perspective):
        if position.ply_count == state.ply_count:
            return {(0, 1): -0.1}
        if position.ply_count == state.ply_count + 1:
            return {(0, 2): -4.0, (1, 2): -0.2}
        raise AssertionError("unexpected position requested")

    def zero_value(self, position, _config, _perspective):
        return 0.0

    search._policy_scores = MethodType(fake_policy_scores, search)  # type: ignore[method-assign]
    search._value_score = MethodType(zero_value, search)  # type: ignore[method-assign]

    turn = search.choose_turn(state, config)

    assert turn.cells == ((0, 1), (1, 2))
