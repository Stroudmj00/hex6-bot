"""Shallow factorized baseline search for Hex6."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hex6.config import AppConfig
from hex6.game import Coord, GameState, IllegalMoveError, Player
from hex6.prototype.candidate_explorer import SparsePosition

from .heuristics import evaluate_state


@dataclass(frozen=True)
class ScoredTurn:
    cells: tuple[Coord, ...]
    score: float
    reply_score: float
    evaluation_score: float
    reason: str


class BaselineTurnSearch:
    """Config-driven shallow search over factorized two-stone turns."""

    def __init__(self) -> None:
        self._candidate_cache: dict[tuple[Any, ...], list[Any]] = {}
        self._evaluation_cache: dict[tuple[Any, ...], Any] = {}

    def clear_caches(self) -> None:
        self._candidate_cache.clear()
        self._evaluation_cache.clear()

    def choose_turn(self, state: GameState, config: AppConfig) -> ScoredTurn:
        if state.is_terminal:
            raise IllegalMoveError("cannot search from a terminal position")

        if not state.stones and state.placements_remaining == 1:
            return ScoredTurn(
                cells=((0, 0),),
                score=config.heuristic.terminal_score / 10000.0,
                reply_score=0.0,
                evaluation_score=config.heuristic.terminal_score / 10000.0,
                reason="opening_center",
            )

        player = state.to_play
        first_candidates = self.top_candidates(state, config, player)[: config.prototype.first_stone_candidate_limit]

        for first in first_candidates:
            state_after_first = state.apply_placement(first.cell, config.game)
            if state_after_first.winner == player:
                return ScoredTurn(
                    cells=(first.cell,),
                    score=config.heuristic.terminal_score,
                    reply_score=0.0,
                    evaluation_score=config.heuristic.terminal_score,
                    reason="immediate_win",
                )

        if state.placements_remaining == 1:
            best = first_candidates[0]
            return ScoredTurn(
                cells=(best.cell,),
                score=best.total,
                reply_score=0.0,
                evaluation_score=best.total,
                reason="single_step_heuristic",
            )

        own_turns = self.enumerate_turns(
            state,
            config,
            player=player,
            first_width=config.prototype.first_stone_candidate_limit,
            second_width=config.prototype.second_stone_candidate_limit,
        )

        if not own_turns:
            raise IllegalMoveError("no legal turns found from the current state")

        best: ScoredTurn | None = None
        for turn in own_turns:
            state_after_turn = self.apply_cells(state, turn.cells, config)
            if state_after_turn.winner == player:
                scored = ScoredTurn(
                    cells=turn.cells,
                    score=config.heuristic.terminal_score,
                    reply_score=0.0,
                    evaluation_score=config.heuristic.terminal_score,
                    reason="immediate_win",
                )
            else:
                evaluation = evaluate_state(state_after_turn, config, player)
                opponent_reply = self.worst_reply_score(state_after_turn, config, player)
                combined = opponent_reply
                scored = ScoredTurn(
                    cells=turn.cells,
                    score=round(combined, 3),
                    reply_score=round(opponent_reply, 3),
                    evaluation_score=evaluation.total,
                    reason="reply_aware",
                )

            if best is None or scored.score > best.score:
                best = scored

        return best

    def enumerate_turns(
        self,
        state: GameState,
        config: AppConfig,
        player: Player,
        first_width: int,
        second_width: int,
    ) -> list[ScoredTurn]:
        first_candidates = self.top_candidates(state, config, player)[:first_width]
        turns: list[ScoredTurn] = []
        seen: set[tuple[Coord, ...]] = set()

        for first in first_candidates:
            state_after_first = state.apply_placement(first.cell, config.game)
            if state_after_first.winner == player or state_after_first.to_play != player:
                cells = (first.cell,)
                if cells not in seen:
                    seen.add(cells)
                    turns.append(
                        ScoredTurn(
                            cells=cells,
                            score=0.0,
                            reply_score=0.0,
                            evaluation_score=0.0,
                            reason="forced_single",
                        )
                    )
                continue

            second_candidates = self.top_candidates(state_after_first, config, player)[:second_width]
            for second in second_candidates:
                if second.cell == first.cell:
                    continue
                cells = tuple(sorted((first.cell, second.cell)))
                if cells in seen:
                    continue
                seen.add(cells)
                turns.append(
                    ScoredTurn(
                        cells=cells,
                        score=0.0,
                        reply_score=0.0,
                        evaluation_score=0.0,
                        reason="pair",
                    )
                )

        return turns

    def worst_reply_score(self, state: GameState, config: AppConfig, root_player: Player) -> float:
        if state.is_terminal:
            return 0.0

        opponent = state.to_play
        replies = self.enumerate_turns(
            state,
            config,
            player=opponent,
            first_width=config.search.shallow_reply_width,
            second_width=config.prototype.second_stone_candidate_limit,
        )
        if not replies:
            return self.evaluate_cached(state, config, root_player).total

        worst = float("inf")
        for reply in replies:
            reply_state = self.apply_cells(state, reply.cells, config)
            evaluation = self.evaluate_cached(reply_state, config, root_player)
            worst = min(worst, evaluation.total)
        return worst

    def top_candidates(self, state: GameState, config: AppConfig, player: Player) -> list[Any]:
        key = ("candidates", state.signature(), player)
        cached = self._candidate_cache.get(key)
        if cached is not None:
            return cached

        position = SparsePosition.from_game_state(state)
        scored = position.top_first_stone_candidates(config, player)
        self._candidate_cache[key] = scored
        return scored

    def evaluate_cached(self, state: GameState, config: AppConfig, player: Player) -> Any:
        key = ("evaluation", state.signature(), player)
        cached = self._evaluation_cache.get(key)
        if cached is not None:
            return cached

        evaluation = evaluate_state(state, config, player)
        self._evaluation_cache[key] = evaluation
        return evaluation

    @staticmethod
    def apply_cells(state: GameState, cells: tuple[Coord, ...], config: AppConfig) -> GameState:
        current = state
        for cell in cells:
            current = current.apply_placement(cell, config.game)
        return current
