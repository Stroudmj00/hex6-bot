"""Shallow factorized baseline search for Hex6."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from types import SimpleNamespace
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
        self._immediate_turn_cache: dict[tuple[Any, ...], list[tuple[Coord, ...]]] = {}
        self._reply_score_cache: dict[tuple[Any, ...], float] = {}
        self._followup_score_cache: dict[tuple[Any, ...], float] = {}

    def clear_caches(self) -> None:
        self._candidate_cache.clear()
        self._evaluation_cache.clear()
        self._immediate_turn_cache.clear()
        self._reply_score_cache.clear()
        self._followup_score_cache.clear()

    def choose_turn(self, state: GameState, config: AppConfig) -> ScoredTurn:
        if state.is_terminal:
            raise IllegalMoveError("cannot search from a terminal position")

        if not state.stones and state.placements_remaining == 1:
            return ScoredTurn(
                cells=(config.game.opening_cell(),),
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
        reply_depth = self._reply_depth(config)
        first_candidates = self.top_candidates(state, config, player)[: config.prototype.first_stone_candidate_limit]

        for first in first_candidates:
            state_after_first = state.apply_placement(first.cell, config.game, record_history=False)
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
                state_after_first = state.apply_placement(first.cell, config.game, record_history=False)
                if state_after_first.winner == player:
                    scored = ScoredTurn(
                        cells=(first.cell,),
                        score=config.heuristic.terminal_score,
                        reply_score=0.0,
                        evaluation_score=config.heuristic.terminal_score,
                        reason="immediate_win",
                    )
                else:
                    opponent_reply = self.worst_reply_score(
                        state_after_first,
                        config,
                        player,
                        remaining_depth=reply_depth,
                    )
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
                opponent_reply = self.worst_reply_score(
                    state_after_turn,
                    config,
                    player,
                    remaining_depth=reply_depth,
                )
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
        immediate_turns = self._find_immediate_turns(
            state,
            config,
            player,
            state.placements_remaining,
        )
        if immediate_turns:
            winning_cells = immediate_turns[0]
            return ScoredTurn(
                cells=winning_cells,
                score=config.heuristic.terminal_score,
                reply_score=0.0,
                evaluation_score=config.heuristic.terminal_score,
                reason="immediate_win",
            )

        opponent = state.opponent()
        opponent_immediate_turns = self._find_immediate_turns(
            state,
            config,
            opponent,
            config.game.turn_placements,
        )
        if opponent_immediate_turns:
            forced_defense = self._defensive_turns(state, config, player, opponent_immediate_turns)
            if forced_defense:
                return self._score_turns(state, config, player, forced_defense, reason="forced_defense")

        forcing_attack = self._choose_forcing_attack(state, config, player)
        if forcing_attack is not None:
            return forcing_attack

        return self._choose_turn_heuristic(state, config)

    def _choose_forcing_attack(
        self,
        state: GameState,
        config: AppConfig,
        player: Player,
    ) -> ScoredTurn | None:
        own_turns = self.enumerate_turns(
            state,
            config,
            player=player,
            first_width=config.prototype.first_stone_candidate_limit,
            second_width=config.prototype.second_stone_candidate_limit,
        )

        best: ScoredTurn | None = None
        best_threat_count = -1
        forcing_score = config.heuristic.terminal_score - 1.0
        for turn in own_turns:
            state_after_turn = self.apply_cells(state, turn.cells, config)
            if state_after_turn.winner == player:
                continue

            threats = self._find_immediate_turns(
                state_after_turn,
                config,
                player,
                config.game.turn_placements,
            )
            if not threats:
                continue

            defenses = self._defensive_turns(
                state_after_turn,
                config,
                state_after_turn.to_play,
                threats,
            )
            if defenses:
                continue

            evaluation = self.evaluate_cached(state_after_turn, config, player)
            scored = ScoredTurn(
                cells=turn.cells,
                score=forcing_score,
                reply_score=forcing_score,
                evaluation_score=evaluation.total,
                reason="forcing_attack",
            )
            if (
                best is None
                or len(threats) > best_threat_count
                or (
                    len(threats) == best_threat_count
                    and (
                        scored.evaluation_score > best.evaluation_score
                        or (
                            scored.evaluation_score == best.evaluation_score
                            and scored.cells < best.cells
                        )
                    )
                )
            ):
                best = scored
                best_threat_count = len(threats)

        return best

    def _score_turns(
        self,
        state: GameState,
        config: AppConfig,
        player: Player,
        turns: list[tuple[Coord, ...]],
        reason: str,
    ) -> ScoredTurn:
        best: ScoredTurn | None = None
        reply_depth = self._reply_depth(config)
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
                opponent_reply = self.worst_reply_score(
                    state_after_turn,
                    config,
                    player,
                    remaining_depth=reply_depth,
                )
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
            state_after_first = state.apply_placement(first.cell, config.game, record_history=False)
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

    def _find_immediate_turns(
        self,
        state: GameState,
        config: AppConfig,
        player: Player,
        placements_available: int,
    ) -> list[tuple[Coord, ...]]:
        key = (
            "immediate_turns",
            state.signature(),
            player,
            placements_available,
            self._config_cache_key(config),
        )
        cached = self._immediate_turn_cache.get(key)
        if cached is not None:
            return cached

        position = SparsePosition.from_game_state(state)
        immediate: list[tuple[Coord, ...]] = []
        seen: set[tuple[Coord, ...]] = set()
        for summary in position.open_windows(config, player):
            if summary.empty_count == 0 or summary.empty_count > placements_available:
                continue
            cells = tuple(sorted(cell for cell in summary.cells if state.is_empty(cell)))
            if cells in seen:
                continue
            seen.add(cells)
            immediate.append(cells)

        immediate.sort(key=lambda cells: (len(cells), cells))
        self._immediate_turn_cache[key] = immediate
        return immediate

    def _defensive_turns(
        self,
        state: GameState,
        config: AppConfig,
        player: Player,
        threats: list[tuple[Coord, ...]],
    ) -> list[tuple[Coord, ...]]:
        critical_cells = sorted({cell for threat in threats for cell in threat if state.is_empty(cell)})
        if not critical_cells:
            return []

        blocking_sets: list[tuple[Coord, ...]] = []
        for size in range(1, min(len(critical_cells), state.placements_remaining) + 1):
            size_matches: list[tuple[Coord, ...]] = []
            for combo in combinations(critical_cells, size):
                if self._blocks_all_threats(combo, threats):
                    size_matches.append(combo)
            if size_matches:
                blocking_sets = size_matches
                break

        if not blocking_sets:
            return []

        turns: list[tuple[Coord, ...]] = []
        seen: set[tuple[Coord, ...]] = set()
        filler_pool = self._candidate_pool(state, config, player, critical_cells)
        for combo in blocking_sets:
            if len(combo) == state.placements_remaining:
                ordered = tuple(sorted(combo))
                if ordered not in seen:
                    seen.add(ordered)
                    turns.append(ordered)
                continue

            remaining_slots = state.placements_remaining - len(combo)
            filler_candidates = [cell for cell in filler_pool if cell not in combo]
            for fillers in combinations(filler_candidates, remaining_slots):
                ordered = tuple(sorted(combo + fillers))
                if ordered in seen:
                    continue
                seen.add(ordered)
                turns.append(ordered)

        return turns

    def _candidate_pool(
        self,
        state: GameState,
        config: AppConfig,
        player: Player,
        critical_cells: list[Coord],
    ) -> list[Coord]:
        position = SparsePosition.from_game_state(state)
        ranked = [candidate.cell for candidate in self.top_candidates(state, config, player)]
        frontier = sorted(
            cell
            for cell in position.frontier_cells(max(1, config.prototype.frontier_distance), config.game)
            if state.is_empty(cell)
        )
        extras = ranked + critical_cells + frontier
        if len(extras) < max(4, len(critical_cells) + state.placements_remaining):
            extras.extend(
                cell
                for cell in sorted(position.analysis_cells(config))
                if state.is_empty(cell)
            )

        pool: list[Coord] = []
        seen: set[Coord] = set()
        for cell in extras:
            if cell in seen:
                continue
            seen.add(cell)
            pool.append(cell)
        return pool

    @staticmethod
    def _blocks_all_threats(turn: tuple[Coord, ...], threats: list[tuple[Coord, ...]]) -> bool:
        chosen = set(turn)
        return all(any(cell in chosen for cell in threat) for threat in threats)

    def worst_reply_score(
        self,
        state: GameState,
        config: AppConfig,
        root_player: Player,
        *,
        remaining_depth: int | None = None,
    ) -> float:
        remaining_depth = remaining_depth if remaining_depth is not None else self._reply_depth(config)
        key = (
            "reply_score",
            state.signature(),
            root_player,
            remaining_depth,
            self._config_cache_key(config),
        )
        cached = self._reply_score_cache.get(key)
        if cached is not None:
            return cached
        if state.is_terminal:
            score = self.evaluate_cached(state, config, root_player).total
            self._reply_score_cache[key] = score
            return score

        opponent = state.to_play
        if config.search.tactical_solver == "threat_search":
            immediate_replies = self._find_immediate_turns(
                state,
                config,
                opponent,
                state.placements_remaining,
            )
            if immediate_replies:
                score = -config.heuristic.terminal_score
                self._reply_score_cache[key] = score
                return score
        replies = self.enumerate_turns(
            state,
            config,
            player=opponent,
            first_width=config.search.shallow_reply_width,
            second_width=config.prototype.second_stone_candidate_limit,
        )
        if not replies:
            score = self.evaluate_cached(state, config, root_player).total
            self._reply_score_cache[key] = score
            return score

        worst = float("inf")
        for reply in replies:
            reply_state = self.apply_cells(state, reply.cells, config)
            worst = min(
                worst,
                self._score_reply_state(
                    reply_state,
                    config,
                    root_player,
                    remaining_depth=remaining_depth,
                ),
            )
            if worst <= -config.heuristic.terminal_score:
                break
        self._reply_score_cache[key] = worst
        return worst

    def _score_reply_state(
        self,
        state: GameState,
        config: AppConfig,
        root_player: Player,
        *,
        remaining_depth: int,
    ) -> float:
        if config.search.tactical_solver == "threat_search":
            root_immediate_turns = self._find_immediate_turns(
                state,
                config,
                root_player,
                state.placements_remaining,
            )
            if root_immediate_turns:
                return config.heuristic.terminal_score - 1.0

        if remaining_depth > 1 and not state.is_terminal:
            return self._best_followup_score(
                state,
                config,
                root_player,
                remaining_depth=remaining_depth - 1,
            )

        return self.evaluate_cached(state, config, root_player).total

    def _best_followup_score(
        self,
        state: GameState,
        config: AppConfig,
        root_player: Player,
        *,
        remaining_depth: int,
    ) -> float:
        key = (
            "followup_score",
            state.signature(),
            root_player,
            remaining_depth,
            self._config_cache_key(config),
        )
        cached = self._followup_score_cache.get(key)
        if cached is not None:
            return cached
        if state.is_terminal:
            score = self.evaluate_cached(state, config, root_player).total
            self._followup_score_cache[key] = score
            return score

        player = state.to_play
        if player != root_player:
            score = self.worst_reply_score(
                state,
                config,
                root_player,
                remaining_depth=remaining_depth,
            )
            self._followup_score_cache[key] = score
            return score

        if config.search.tactical_solver == "threat_search":
            immediate_turns = self._find_immediate_turns(
                state,
                config,
                player,
                state.placements_remaining,
            )
            if immediate_turns:
                score = config.heuristic.terminal_score
                self._followup_score_cache[key] = score
                return score

        if state.placements_remaining == 1:
            first_candidates = self.top_candidates(state, config, player)[: config.prototype.first_stone_candidate_limit]
            if not first_candidates:
                score = self.evaluate_cached(state, config, root_player).total
                self._followup_score_cache[key] = score
                return score

            best = float("-inf")
            for first in first_candidates:
                state_after_first = state.apply_placement(first.cell, config.game, record_history=False)
                if state_after_first.winner == player:
                    score = config.heuristic.terminal_score
                    self._followup_score_cache[key] = score
                    return score
                best = max(
                    best,
                    self.worst_reply_score(
                        state_after_first,
                        config,
                        root_player,
                        remaining_depth=remaining_depth,
                    ),
                )
                if best >= config.heuristic.terminal_score:
                    break
            self._followup_score_cache[key] = best
            return best

        own_turns = self.enumerate_turns(
            state,
            config,
            player=player,
            first_width=config.prototype.first_stone_candidate_limit,
            second_width=config.prototype.second_stone_candidate_limit,
        )
        if not own_turns:
            score = self.evaluate_cached(state, config, root_player).total
            self._followup_score_cache[key] = score
            return score

        best = float("-inf")
        for turn in own_turns:
            state_after_turn = self.apply_cells(state, turn.cells, config)
            if state_after_turn.winner == player:
                score = config.heuristic.terminal_score
                self._followup_score_cache[key] = score
                return score
            best = max(
                best,
                self.worst_reply_score(
                    state_after_turn,
                    config,
                    root_player,
                    remaining_depth=remaining_depth,
                ),
            )
            if best >= config.heuristic.terminal_score:
                break
        self._followup_score_cache[key] = best
        return best

    @staticmethod
    def _reply_depth(config: AppConfig) -> int:
        if config.search.reply_depth < 1:
            raise ValueError(f"search.reply_depth must be >= 1, received {config.search.reply_depth}")
        return config.search.reply_depth

    def top_candidates(self, state: GameState, config: AppConfig, player: Player) -> list[Any]:
        key = ("candidates", state.signature(), player, self._config_cache_key(config))
        cached = self._candidate_cache.get(key)
        if cached is not None:
            return cached

        position = SparsePosition.from_game_state(state)
        scored = position.top_first_stone_candidates(config, player)
        if not scored:
            scored = [
                SimpleNamespace(cell=cell, total=0.0)
                for cell in self._fallback_empty_cells(state, config)
            ]
        self._candidate_cache[key] = scored
        return scored

    def evaluate_cached(self, state: GameState, config: AppConfig, player: Player) -> Any:
        key = ("evaluation", state.signature(), player, self._config_cache_key(config))
        cached = self._evaluation_cache.get(key)
        if cached is not None:
            return cached

        evaluation = evaluate_state(state, config, player)
        self._evaluation_cache[key] = evaluation
        return evaluation

    @staticmethod
    def _fallback_empty_cells(state: GameState, config: AppConfig) -> list[Coord]:
        bounds = config.game.bounds()
        if bounds is not None:
            min_q, max_q, min_r, max_r = bounds
            empties = [
                (q, r)
                for q in range(min_q, max_q + 1)
                for r in range(min_r, max_r + 1)
                if state.is_empty((q, r))
            ]
            empties.sort()
            return empties

        position = SparsePosition.from_game_state(state)
        empties = sorted(cell for cell in position.analysis_cells(config) if state.is_empty(cell))
        if empties:
            return empties

        frontier = sorted(
            cell
            for cell in position.frontier_cells(max(1, config.prototype.frontier_distance), config.game)
            if state.is_empty(cell)
        )
        if frontier:
            return frontier

        opening = config.game.opening_cell()
        return [opening] if state.is_empty(opening) else []

    @staticmethod
    def _config_cache_key(config: AppConfig) -> tuple[Any, ...]:
        return (
            config.game,
            config.prototype,
            config.scoring,
            config.heuristic,
            config.search,
        )

    @staticmethod
    def apply_cells(state: GameState, cells: tuple[Coord, ...], config: AppConfig) -> GameState:
        current = state
        for cell in cells:
            current = current.apply_placement(cell, config.game, record_history=False)
            if current.is_terminal:
                return current
        return current
