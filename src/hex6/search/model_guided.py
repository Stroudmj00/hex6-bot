"""Model-guided shallow search for checkpoint evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import torch

from hex6.config import AppConfig
from hex6.game import Coord, GameState, IllegalMoveError, Player
from hex6.nn import HexPolicyValueNet, encode_state, load_compatible_state_dict

from .baseline import BaselineTurnSearch, ScoredTurn


@dataclass(frozen=True)
class ModelTurnScore:
    turn: ScoredTurn
    combined: float
    policy_score: float
    value_score: float
    heuristic_score: float


class ModelGuidedTurnSearch:
    """Use a trained checkpoint to re-rank heuristic candidate turns."""

    def __init__(
        self,
        model: HexPolicyValueNet,
        *,
        device: torch.device,
        baseline: BaselineTurnSearch | None = None,
    ) -> None:
        self._model = model.eval()
        self._device = device
        self._baseline = baseline or BaselineTurnSearch()
        self._policy_cache: dict[tuple[object, ...], dict[Coord, float]] = {}
        self._value_cache: dict[tuple[object, ...], float] = {}

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint_path: str | Path,
        config: AppConfig,
        *,
        device: torch.device | None = None,
        baseline: BaselineTurnSearch | None = None,
    ) -> "ModelGuidedTurnSearch":
        device = device or _select_device(config)
        checkpoint = torch.load(checkpoint_path, map_location=device)
        model = HexPolicyValueNet(
            input_channels=6,
            channels=config.model.channels,
            blocks=config.model.blocks,
        )
        load_compatible_state_dict(model, checkpoint["model_state_dict"])
        model.to(device)
        return cls(model, device=device, baseline=baseline)

    def choose_turn(self, state: GameState, config: AppConfig) -> ScoredTurn:
        if state.is_terminal:
            raise IllegalMoveError("cannot search from a terminal position")
        if not state.stones and state.placements_remaining == 1:
            return self._baseline.choose_turn(state, config)

        player = state.to_play
        candidate_turns = self._baseline.enumerate_turns(
            state,
            config,
            player=player,
            first_width=config.prototype.first_stone_candidate_limit,
            second_width=config.prototype.second_stone_candidate_limit,
        )
        if not candidate_turns:
            raise IllegalMoveError("no legal turns found from the current state")

        best_score: ModelTurnScore | None = None

        for turn in candidate_turns:
            state_after_turn = self._baseline.apply_cells(state, turn.cells, config)
            if state_after_turn.winner == player:
                return ScoredTurn(
                    cells=turn.cells,
                    score=config.heuristic.terminal_score,
                    reply_score=0.0,
                    evaluation_score=config.heuristic.terminal_score,
                    reason="model_immediate_win",
                )

            policy_score = self._turn_policy_score(state, turn.cells, config, player)
            value_score = self._value_score(state_after_turn, config, player)
            heuristic_score = self._baseline.evaluate_cached(state_after_turn, config, player).total
            combined = (
                config.evaluation.model_policy_weight * policy_score
                + config.evaluation.model_value_weight * value_score
                + config.evaluation.model_heuristic_weight * heuristic_score
            )
            scored = ModelTurnScore(
                turn=turn,
                combined=round(combined, 4),
                policy_score=round(policy_score, 4),
                value_score=round(value_score, 4),
                heuristic_score=round(heuristic_score, 4),
            )
            if best_score is None or scored.combined > best_score.combined:
                best_score = scored

        assert best_score is not None
        return ScoredTurn(
            cells=best_score.turn.cells,
            score=best_score.combined,
            reply_score=best_score.value_score,
            evaluation_score=best_score.heuristic_score,
            reason="model_guided",
        )

    def _policy_scores(
        self,
        state: GameState,
        config: AppConfig,
        perspective: Player,
    ) -> dict[Coord, float]:
        key = ("policy", state.signature(), perspective)
        cached = self._policy_cache.get(key)
        if cached is not None:
            return cached

        encoded = encode_state(state, config, perspective=perspective)
        with torch.inference_mode():
            policy_logits, _ = self._model(encoded.tensor.unsqueeze(0).to(self._device))
        log_probs = torch.log_softmax(policy_logits.squeeze(0).cpu(), dim=0)
        scores: dict[Coord, float] = {}
        for index, cell in enumerate(encoded.index_to_cell):
            scores[cell] = float(log_probs[index])
        self._policy_cache[key] = scores
        return scores

    def _turn_policy_score(
        self,
        state: GameState,
        cells: tuple[Coord, ...],
        config: AppConfig,
        perspective: Player,
    ) -> float:
        current_state = state
        scores: list[float] = []
        for cell in cells:
            scores.append(self._policy_scores(current_state, config, perspective).get(cell, -12.0))
            current_state = current_state.apply_placement(cell, config.game, record_history=False)
            if current_state.is_terminal:
                break
        return sum(scores) / max(len(scores), 1)

    def _value_score(self, state: GameState, config: AppConfig, perspective: Player) -> float:
        key = ("value", state.signature(), perspective)
        cached = self._value_cache.get(key)
        if cached is not None:
            return cached

        encoded = encode_state(state, config, perspective=perspective)
        with torch.inference_mode():
            _, value = self._model(encoded.tensor.unsqueeze(0).to(self._device))
        score = float(value.squeeze(0).cpu())
        self._value_cache[key] = score
        return score


def load_checkpoint_metadata(checkpoint_path: str | Path) -> dict[str, object]:
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    return {
        "config_path": checkpoint.get("config_path"),
        "history": checkpoint.get("history", []),
    }


def _select_device(config: AppConfig) -> torch.device:
    if config.runtime.preferred_device == "cuda" and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")
