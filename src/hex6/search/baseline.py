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

        if config.search.tactical_solver == "threat_search":
            return self._choose_turn_with_threat_search(state, config)

        return self._choose_turn_heuristic(state, config)

    def _choose_turn_heuristic(self, state: GameState, config: AppConfig) -> ScoredTurn:
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
            best: ScoredTurn | None = None
            for first in first_candidates:
                state_after_first = state.apply_placement(first.cell, config.game)
                if state_after_first.winner == player:
                    scored = ScoredTurn(
                        cells=(first.cell,),
                        score=config.heuristic.terminal_score,
                        reply_score=0.0,
                        evaluation_score=config.heuristic.terminal_score,
                        reason="immediate_win",
                    )
                else:
                    opponent_reply = self.worst_reply_score(state_after_first, config, player)
                    evaluation = self.evaluate_cached(state_after_first, config, player)
                    scored = ScoredTurn(
                        cells=(first.cell,),
                        score=round(opponent_reply, 3),
                        reply_score=round(opponent_reply, 3),
                        evaluation_score=evaluation.total,
                        reason="single_step_heuristic",
                    )

                if best is None or scored.score > best.score:
                    best = scored

            if best is None:
                raise IllegalMoveError("no legal turns found from the current state")
            return best

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

    def _choose_turn_with_threat_search(self, state: GameState, config: AppConfig) -> ScoredTurn:
        player = state.to_play
        candidates = self._all_candidate_cells(state, config)

        immediate_turns = self._find_immediate_turns(state, config, player, candidates)
        if immediate_turns:
            winning_cells = immediate_turns[0]
            return ScoredTurn(
                cells=winning_cells,
                score=config.heuristic.terminal_score,
                reply_score=0.0,
                evaluation_score=config.heuristic.terminal_score,
                reason="immediate_win",
            )

        all_turns = self._enumerate_turns(state, config, player, candidates=candidates)
        if not all_turns:
            raise IllegalMoveError("no legal turns found from the current state")

        forced_defense: list[tuple[Coord, ...]] = []
        opponent = state.opponent()
        opponent_start_state = self._as_player_state(state, opponent)
        opponent_immediate_turns = self._find_immediate_turns(
            opponent_start_state, config, opponent, candidates
        )

        if opponent_immediate_turns:
            for turn in all_turns:
                if self._blocks_all_threats(turn, opponent_immediate_turns):
                    forced_defense.append(turn)

        if forced_defense:
            return self._score_turns(state, config, player, forced_defense, reason="forced_defense")

        return self._choose_turn_heuristic(state, config)

    def _score_turns(
        self,
        state: GameState,
        config: AppConfig,
        player: Player,
        turns: list[tuple[Coord, ...]],
        reason: str,
    ) -> ScoredTurn:
        best: ScoredTurn | None = None
        for cells in turns:
            state_after_turn = self.apply_cells(state, cells, config)
            if state_after_turn.winner == player:
                scored = ScoredTurn(
                    cells=cells,
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
                    cells=cells,
                    score=round(combined, 3),
                    reply_score=round(opponent_reply, 3),
                    evaluation_score=evaluation.total,
                    reason=reason,
                )

            if best is None or scored.score > best.score:
                best = scored

        if best is None:
            raise IllegalMoveError("no legal turns found from the current state")
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

    def _enumerate_turns(self, state: GameState, config: AppConfig, player: Player, candidates: tuple[Coord, ...]) -> list[tuple[Coord, ...]]:
        turns: list[tuple[Coord, ...]] = []
        seen: set[tuple[Coord, ...]] = set()

        if state.placements_remaining == 1:
            for first in candidates:
                if first in state.stones:
                    continue
                turn = (first,)
                if turn in seen:
                    continue
                seen.add(turn)
                turns.append(turn)
            return turns

        for index, first in enumerate(candidates):
            if first in state.stones:
                continue
            state_after_first = state.apply_placement(first, config.game)
            if state_after_first.winner == player or state_after_first.to_play != player:
                turn = (first,)
                if turn not in seen:
                    seen.add(turn)
                    turns.append(turn)
                continue

            for second in candidates[index + 1 :]:
                if second == first or second in state.stones:
                    continue
                try:
                    state_after_second = state_after_first.apply_placement(second, config.game)
                except IllegalMoveError:
                    continue
                cells = (first, second)
                if state_after_second.winner == player or state_after_second.to_play != player:
                    pass
                if cells in seen:
                    continue
                seen.add(cells)
                turns.append(tuple(sorted(cells)))

        return turns

    def _all_candidate_cells(self, state: GameState, config: AppConfig) -> tuple[Coord, ...]:
        position = SparsePosition.from_game_state(state)
        return tuple(sorted(cell for cell in position.analysis_cells(config) if state.is_empty(cell)))

    def _find_immediate_turns(
        self,
        state: GameState,
        config: AppConfig,
        player: Player,
        candidates: tuple[Coord, ...],
    ) -> list[tuple[Coord, ...]]:
        state_for_player = self._as_player_state(state, player)
        if state.placements_remaining == 1:
            immediate: list[tuple[Coord, ...]] = []
            for cell in candidates:
                if not state_for_player.is_empty(cell):
                    continue
                if state_for_player.apply_placement(cell, config.game).winner == player:
                    immediate.append((cell,))
            return immediate

        if state.placements_remaining != 2:
            return []

        immediate: list[tuple[Coord, ...]] = []
        for index, first in enumerate(candidates):
            if not state_for_player.is_empty(first):
                continue
            state_after_first = state_for_player.apply_placement(first, config.game)
            if state_after_first.winner == player:
                immediate.append((first,))
                continue
            for second in candidates[index + 1 :]:
                if not state_after_first.is_empty(second):
                    continue
                if state_after_first.apply_placement(second, config.game).winner == player:
                    immediate.append(tuple(sorted((first, second))))

        immediate.sort(key=lambda cells: (len(cells), cells))
        return immediate

    def _as_player_state(self, state: GameState, player: Player) -> GameState:
        if state.to_play == player:
            return state

        return GameState(
            stones=state.stones,
            to_play=player,
            placements_remaining=state.placements_remaining,
            turn_index=state.turn_index,
            ply_count=state.ply_count,
            winner=state.winner,
            winning_line=state.winning_line,
            move_history=state.move_history,
        )

    def _blocks_all_threats(self, turn: tuple[Coord, ...], threats: list[tuple[Coord, ...]]) -> bool:
        for threat in threats:
            if not any(cell in threat for cell in turn):
                return False
        return True

    def worst_reply_score(self, state: GameState, config: AppConfig, root_player: Player) -> float:
        if state.is_terminal:
            return self.evaluate_cached(state, config, root_player).total

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
            if current.is_terminal:
                return current
        return current
