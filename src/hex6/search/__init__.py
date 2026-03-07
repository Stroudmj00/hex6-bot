"""Search baselines and evaluation helpers."""

from typing import TYPE_CHECKING

from .baseline import BaselineTurnSearch, ScoredTurn
from .heuristics import HeuristicEvaluation, evaluate_state

if TYPE_CHECKING:
    from .model_guided import ModelGuidedTurnSearch

__all__ = [
    "BaselineTurnSearch",
    "HeuristicEvaluation",
    "ModelGuidedTurnSearch",
    "ScoredTurn",
    "evaluate_state",
]


def __getattr__(name: str):
    if name == "ModelGuidedTurnSearch":
        from .model_guided import ModelGuidedTurnSearch

        return ModelGuidedTurnSearch
    raise AttributeError(name)
