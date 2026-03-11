"""Search baselines and evaluation helpers."""

from typing import TYPE_CHECKING

from .baseline import BaselineTurnSearch, ScoredTurn
from .guided_mcts import GuidedMctsTurnSearch, RootAnalysis, RootTurnStat
from .heuristics import HeuristicEvaluation, evaluate_state

if TYPE_CHECKING:
    from .model_guided import ModelGuidedTurnSearch

__all__ = [
    "BaselineTurnSearch",
    "GuidedMctsTurnSearch",
    "HeuristicEvaluation",
    "ModelGuidedTurnSearch",
    "RootAnalysis",
    "RootTurnStat",
    "ScoredTurn",
    "evaluate_state",
]


def __getattr__(name: str):
    if name == "ModelGuidedTurnSearch":
        from .model_guided import ModelGuidedTurnSearch

        return ModelGuidedTurnSearch
    raise AttributeError(name)
