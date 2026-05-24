"""Shallow factorized baseline search for Hex6."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from types import SimpleNamespace
from typing import Any

from hex6.config import AppConfig
from hex6.game import Coord, GameState, IllegalMoveError, Player, hex_distance
from hex6.prototype.candidate_explorer import SparsePosition

from .heuristics import evaluate_state


@dataclass(frozen=True)
class ScoredTurn:
    cells: tuple[Coord, ...]
    score: float
    reply_score: float
    evaluation_score: float
    reason: str


@dataclass(frozen=True)
class TacticalTurnAnalysis:
    forced_turn: ScoredTurn | None = None
    proactive_build: ScoredTurn | None = None


class BaselineTurnSearch:
    """Config-driven shallow search over factorized two-stone turns."""

    def __init__(self) -> None:
        self._position_cache: dict[tuple[Any, ...], SparsePosition] = {}
        self._candidate_cache: dict[tuple[Any, ...], list[Any]] = {}
        self._open_window_cache: dict[tuple[Any, ...], tuple[Any, ...]] = {}
        self._evaluation_cache: dict[tuple[Any, ...], Any] = {}
        self._immediate_turn_cache: dict[tuple[Any, ...], list[tuple[Coord, ...]]] = {}
        self._pre_immediate_turn_cache: dict[tuple[Any, ...], list[tuple[Coord, ...]]] = {}
        self._pre_immediate_cluster_cache: dict[tuple[Any, ...], tuple[tuple[tuple[Coord, ...], ...], ...]] = {}
        self._reply_score_cache: dict[tuple[Any, ...], float] = {}
        self._followup_score_cache: dict[tuple[Any, ...], float] = {}

    def clear_caches(self) -> None:
        self._position_cache.clear()
        self._candidate_cache.clear()
        self._open_window_cache.clear()
        self._evaluation_cache.clear()
        self._immediate_turn_cache.clear()
        self._pre_immediate_turn_cache.clear()
        self._pre_immediate_cluster_cache.clear()
        self._reply_score_cache.clear()
        self._followup_score_cache.clear()

    def _position_for_state(self, state: GameState) -> SparsePosition:
        key = ("position", state.signature())
        cached = self._position_cache.get(key)
        if cached is not None:
            return cached
        position = SparsePosition.from_game_state(state)
        self._position_cache[key] = position
        return position

    def _open_windows_for_player(
        self,
        state: GameState,
        config: AppConfig,
        player: Player,
    ) -> tuple[Any, ...]:
        key = ("open_windows", state.signature(), player, self._config_cache_key(config))
        cached = self._open_window_cache.get(key)
        if cached is not None:
            return cached
        position = self._position_for_state(state)
        windows = tuple(position.open_windows(config, player))
        self._open_window_cache[key] = windows
        return windows

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
        tactical = self._analyze_tactical_turns(state, config)
        if tactical.forced_turn is not None:
            return tactical.forced_turn

        heuristic = self._choose_turn_heuristic(state, config)
        if tactical.proactive_build is not None and tactical.proactive_build.score >= heuristic.score:
            return tactical.proactive_build
        return heuristic

    def choose_tactical_turn(
        self,
        state: GameState,
        config: AppConfig,
        *,
        include_proactive_build: bool = False,
        require_remote_proactive_build: bool = False,
    ) -> ScoredTurn | None:
        tactical = self._analyze_tactical_turns(state, config)
        if tactical.forced_turn is not None:
            return tactical.forced_turn
        if include_proactive_build:
            proactive_build = tactical.proactive_build
            if proactive_build is None:
                return None
            if require_remote_proactive_build and not self._is_remote_turn(
                state,
                proactive_build.cells,
                config,
            ):
                return None
            return proactive_build
        return None

    def _analyze_tactical_turns(
        self,
        state: GameState,
        config: AppConfig,
    ) -> TacticalTurnAnalysis:
        player = state.to_play
        immediate_turns = self._find_immediate_turns(
            state,
            config,
            player,
            state.placements_remaining,
        )
        if immediate_turns:
            winning_cells = immediate_turns[0]
            return TacticalTurnAnalysis(
                forced_turn=ScoredTurn(
                    cells=winning_cells,
                    score=config.heuristic.terminal_score,
                    reply_score=0.0,
                    evaluation_score=config.heuristic.terminal_score,
                    reason="immediate_win",
                )
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
                return TacticalTurnAnalysis(
                    forced_turn=self._score_turns(
                        state,
                        config,
                        player,
                        forced_defense,
                        reason="forced_defense",
                    )
                )

        opponent_pre_immediate_turns = self._find_pre_immediate_turns(
            state,
            config,
            opponent,
            config.game.turn_placements,
        )
        if opponent_pre_immediate_turns:
            preemptive_defense = self._preemptive_defense_turns(
                state,
                config,
                player,
                opponent,
            )
            if preemptive_defense:
                return TacticalTurnAnalysis(
                    forced_turn=self._score_turns(
                        state,
                        config,
                        player,
                        preemptive_defense,
                        reason="preemptive_defense",
                    )
                )

        forcing_attack = self._choose_forcing_attack(state, config, player)
        if forcing_attack is not None:
            return TacticalTurnAnalysis(forced_turn=forcing_attack)

        own_pre_immediate_turns = self._find_pre_immediate_turns(
            state,
            config,
            player,
            state.placements_remaining,
        )
        proactive_build = None
        if own_pre_immediate_turns:
            proactive_build = self._score_turns(
                state,
                config,
                player,
                own_pre_immediate_turns,
                reason="pre_immediate_build",
            )
        return TacticalTurnAnalysis(proactive_build=proactive_build)

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
        if config.search.tactical_forcing_turn_cap > 0:
            own_turns = own_turns[: config.search.tactical_forcing_turn_cap]

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
        turns: list[ScoredTurn] = []
        seen: set[tuple[Coord, ...]] = set()

        for cells, reason in self._priority_turns_for_enumeration(
            state,
            config,
            player,
            first_width=first_width,
            second_width=second_width,
        ):
            if cells in seen:
                continue
            seen.add(cells)
            turns.append(
                ScoredTurn(
                    cells=cells,
                    score=0.0,
                    reply_score=0.0,
                    evaluation_score=0.0,
                    reason=reason,
                )
            )

        first_candidates = self.top_candidates(state, config, player)[:first_width]

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

    def _priority_turns_for_enumeration(
        self,
        state: GameState,
        config: AppConfig,
        player: Player,
        *,
        first_width: int,
        second_width: int,
    ) -> list[tuple[tuple[Coord, ...], str]]:
        if config.search.tactical_solver != "threat_search":
            return []

        placements_available = (
            state.placements_remaining if state.to_play == player else config.game.turn_placements
        )
        opponent = state.opponent(player)
        priority_turn_cap = max(1, config.search.tactical_priority_turn_cap)

        ordered: list[tuple[tuple[Coord, ...], str]] = []
        seen: set[tuple[Coord, ...]] = set()

        def add_turns(turns: list[tuple[Coord, ...]], reason: str, *, limit: int | None = None) -> None:
            added = 0
            for cells in turns:
                if cells in seen:
                    continue
                seen.add(cells)
                ordered.append((cells, reason))
                added += 1
                if limit is not None and added >= limit:
                    break

        add_turns(
            self._find_immediate_turns(state, config, player, placements_available),
            "priority_immediate",
        )
        add_turns(
            self._defensive_turns(
                state,
                config,
                player,
                self._find_immediate_turns(
                    state,
                    config,
                    opponent,
                    config.game.turn_placements,
                ),
            ),
            "priority_defense",
        )
        preemptive_defense = self._preemptive_defense_turns(
            state,
            config,
            player,
            opponent,
            limit=priority_turn_cap,
        )
        own_pre_immediate = self._interleave_turn_clusters(
            self._clustered_pre_immediate_turns(
                state,
                config,
                player,
                placements_available,
            ),
            limit=priority_turn_cap,
        )
        depth = 0
        while depth < max(len(preemptive_defense), len(own_pre_immediate)):
            if depth < len(preemptive_defense):
                add_turns(
                    [preemptive_defense[depth]],
                    "priority_preemptive_defense",
                )
            if depth < len(own_pre_immediate):
                add_turns(
                    [own_pre_immediate[depth]],
                    "priority_pre_immediate_build",
                )
            depth += 1
        return ordered

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

        immediate: list[tuple[Coord, ...]] = []
        seen: set[tuple[Coord, ...]] = set()
        for summary in self._open_windows_for_player(state, config, player):
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

    def _find_pre_immediate_turns(
        self,
        state: GameState,
        config: AppConfig,
        player: Player,
        placements_available: int,
    ) -> list[tuple[Coord, ...]]:
        if placements_available <= 0:
            return []

        key = (
            "pre_immediate_turns",
            state.signature(),
            player,
            placements_available,
            self._config_cache_key(config),
        )
        cached = self._pre_immediate_turn_cache.get(key)
        if cached is not None:
            return cached

        max_empty_count = placements_available + config.game.turn_placements
        minimum_friendly = max(1, config.game.win_length - max_empty_count)
        hypothetical = self._state_for_player_turn(state, player, placements_available)
        strength_by_turn: dict[tuple[Coord, ...], tuple[int, int, int, int, int, int]] = {}

        for summary in self._open_windows_for_player(state, config, player):
            if summary.empty_count <= placements_available or summary.empty_count > max_empty_count:
                continue
            if summary.friendly_count < minimum_friendly:
                continue
            empties = tuple(sorted(cell for cell in summary.cells if state.is_empty(cell)))
            for combo in combinations(empties, placements_available):
                ordered = tuple(sorted(combo))
                try:
                    next_state = hypothetical.apply_turn(ordered, config.game, record_history=False)
                except IllegalMoveError:
                    continue
                if next_state.winner == player:
                    continue
                followups = self._find_immediate_turns(
                    next_state,
                    config,
                    player,
                    config.game.turn_placements,
                )
                if not followups:
                    continue
                critical_cell_count = len({cell for turn in followups for cell in turn})
                best_followup = max(
                    config.game.turn_placements + 1 - len(turn)
                    for turn in followups
                )
                edge_bonus = self._bounded_edge_bonus(ordered, config)
                strength = (
                    best_followup,
                    edge_bonus,
                    sum(config.game.turn_placements + 1 - len(turn) for turn in followups),
                    -critical_cell_count,
                    len(followups),
                    summary.friendly_count,
                )
                previous = strength_by_turn.get(ordered)
                if previous is None or strength > previous:
                    strength_by_turn[ordered] = strength

        pre_immediate = sorted(
            strength_by_turn,
            key=lambda cells: (
                -strength_by_turn[cells][0],
                -strength_by_turn[cells][1],
                -strength_by_turn[cells][2],
                -strength_by_turn[cells][3],
                -strength_by_turn[cells][4],
                -strength_by_turn[cells][5],
                cells,
            ),
        )
        if config.search.tactical_pre_immediate_turn_cap > 0:
            pre_immediate = pre_immediate[: config.search.tactical_pre_immediate_turn_cap]
        self._pre_immediate_turn_cache[key] = pre_immediate
        return pre_immediate

    def _clustered_pre_immediate_turns(
        self,
        state: GameState,
        config: AppConfig,
        player: Player,
        placements_available: int,
    ) -> tuple[tuple[tuple[Coord, ...], ...], ...]:
        key = (
            "pre_immediate_clusters",
            state.signature(),
            player,
            placements_available,
            self._config_cache_key(config),
        )
        cached = self._pre_immediate_cluster_cache.get(key)
        if cached is not None:
            return cached

        turns = self._find_pre_immediate_turns(
            state,
            config,
            player,
            placements_available,
        )
        if not turns:
            self._pre_immediate_cluster_cache[key] = ()
            return ()

        hypothetical = self._state_for_player_turn(state, player, placements_available)
        impacts: list[set[Coord]] = []
        for turn in turns:
            next_state = hypothetical.apply_turn(turn, config.game, record_history=False)
            impact = set(turn)
            for followup in self._find_immediate_turns(
                next_state,
                config,
                player,
                config.game.turn_placements,
            ):
                impact.update(followup)
            impacts.append(impact)

        clusters: list[tuple[tuple[Coord, ...], ...]] = []
        remaining = set(range(len(turns)))
        while remaining:
            seed = min(remaining)
            stack = [seed]
            component: list[int] = []
            while stack:
                current = stack.pop()
                if current not in remaining:
                    continue
                remaining.remove(current)
                component.append(current)
                current_impact = impacts[current]
                for other in list(remaining):
                    if current_impact & impacts[other]:
                        stack.append(other)
            component.sort()
            clusters.append(tuple(turns[index] for index in component))

        clustered = tuple(clusters)
        self._pre_immediate_cluster_cache[key] = clustered
        return clustered

    def _preemptive_defense_turns(
        self,
        state: GameState,
        config: AppConfig,
        player: Player,
        opponent: Player,
        *,
        limit: int | None = None,
    ) -> list[tuple[Coord, ...]]:
        clustered_threats = self._clustered_pre_immediate_turns(
            state,
            config,
            opponent,
            config.game.turn_placements,
        )
        if clustered_threats:
            for cluster in clustered_threats:
                focused = self._cluster_focus_turns(
                    state,
                    config,
                    cluster,
                )
                if not focused:
                    continue
                ordered = list(focused[:limit] if limit is not None else focused)
                if ordered:
                    return ordered

        return self._defensive_turns(
            state,
            config,
            player,
            self._find_pre_immediate_turns(
                state,
                config,
                opponent,
                config.game.turn_placements,
            ),
        )

    def _cluster_focus_turns(
        self,
        state: GameState,
        config: AppConfig,
        cluster: tuple[tuple[Coord, ...], ...],
    ) -> tuple[tuple[Coord, ...], ...]:
        if not cluster:
            return ()

        frequencies: dict[Coord, int] = {}
        for turn in cluster:
            for cell in turn:
                if state.is_empty(cell):
                    frequencies[cell] = frequencies.get(cell, 0) + 1
        if not frequencies:
            return ()

        ranked_cells = sorted(
            frequencies,
            key=lambda cell: (-frequencies[cell], cell),
        )
        combo_width = min(
            len(ranked_cells),
            max(state.placements_remaining + 2, state.placements_remaining * 2),
        )
        if config.search.tactical_cluster_cell_cap > 0:
            combo_width = min(
                combo_width,
                max(config.search.tactical_cluster_cell_cap, state.placements_remaining),
            )
        candidate_cells = ranked_cells[:combo_width]
        scored_turns: list[tuple[tuple[int, int], tuple[Coord, ...]]] = []
        seen: set[tuple[Coord, ...]] = set()
        for combo in combinations(candidate_cells, min(len(candidate_cells), state.placements_remaining)):
            ordered = tuple(sorted(combo))
            filled = self._fill_turn_to_full_size(state, config, ordered)
            if not filled or filled in seen:
                continue
            seen.add(filled)
            score = tuple(
                sorted((frequencies.get(cell, 0) for cell in filled), reverse=True)
            )
            scored_turns.append((score, filled))

        scored_turns.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return tuple(turn for _score, turn in scored_turns)

    def _fill_turn_to_full_size(
        self,
        state: GameState,
        config: AppConfig,
        cells: tuple[Coord, ...],
    ) -> tuple[Coord, ...]:
        chosen = list(cells)
        if len(chosen) >= state.placements_remaining:
            filled = tuple(sorted(chosen[: state.placements_remaining]))
            try:
                state.apply_turn(filled, config.game, record_history=False)
            except IllegalMoveError:
                return ()
            return filled
        used = set(chosen)
        for cell in self._fallback_empty_cells(state, config):
            if cell in used:
                continue
            chosen.append(cell)
            used.add(cell)
            if len(chosen) >= state.placements_remaining:
                break
        filled = tuple(sorted(chosen))
        if len(filled) != state.placements_remaining:
            return ()
        try:
            state.apply_turn(filled, config.game, record_history=False)
        except IllegalMoveError:
            return ()
        return filled

    @staticmethod
    def _interleave_turn_clusters(
        clusters: tuple[tuple[tuple[Coord, ...], ...], ...],
        *,
        limit: int | None = None,
    ) -> list[tuple[Coord, ...]]:
        if not clusters:
            return []

        ordered: list[tuple[Coord, ...]] = []
        depth = 0
        while True:
            added = False
            for cluster in clusters:
                if depth >= len(cluster):
                    continue
                ordered.append(cluster[depth])
                added = True
                if limit is not None and len(ordered) >= limit:
                    return ordered
            if not added:
                break
            depth += 1
        return ordered

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
        position = self._position_for_state(state)
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
            if 0 < config.search.tactical_candidate_pool_cap <= len(pool):
                break
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

        position = self._position_for_state(state)
        scored = position.top_first_stone_candidates(config, player)
        priority_cells = self._priority_cells_for_top_candidates(state, config, player)
        if priority_cells:
            prioritized = [SimpleNamespace(cell=cell, total=float("inf")) for cell in priority_cells]
            seen = set(priority_cells)
            prioritized.extend(candidate for candidate in scored if candidate.cell not in seen)
            scored = prioritized
        if not scored:
            scored = [
                SimpleNamespace(cell=cell, total=0.0)
                for cell in self._fallback_empty_cells(state, config)
            ]
        self._candidate_cache[key] = scored
        return scored

    def _priority_cells_for_top_candidates(
        self,
        state: GameState,
        config: AppConfig,
        player: Player,
    ) -> list[Coord]:
        placements_available = state.placements_remaining if state.to_play == player else config.game.turn_placements
        own_immediate = self._find_immediate_turns(state, config, player, placements_available)
        opponent = state.opponent(player)
        opponent_immediate = self._find_immediate_turns(
            state,
            config,
            opponent,
            config.game.turn_placements,
        )
        opponent_pressure = self._pressure_window_cells(
            state,
            config,
            opponent,
            config.game.turn_placements,
        )
        own_pressure = self._pressure_window_cells(
            state,
            config,
            player,
            placements_available,
        )
        opponent_pre_immediate = self._interleave_turn_clusters(
            self._clustered_pre_immediate_turns(
                state,
                config,
                opponent,
                config.game.turn_placements,
            )
        )
        own_pre_immediate = self._interleave_turn_clusters(
            self._clustered_pre_immediate_turns(
                state,
                config,
                player,
                placements_available,
            )
        )

        ordered: list[Coord] = []
        seen: set[Coord] = set()
        for turns in (
            own_immediate,
            opponent_immediate,
            tuple((cell,) for cell in opponent_pressure),
            tuple((cell,) for cell in own_pressure),
            opponent_pre_immediate,
            own_pre_immediate,
        ):
            for cells in turns:
                for cell in cells:
                    if not state.is_empty(cell) or cell in seen:
                        continue
                    seen.add(cell)
                    ordered.append(cell)
        return ordered

    def _pressure_window_cells(
        self,
        state: GameState,
        config: AppConfig,
        player: Player,
        placements_available: int,
    ) -> list[Coord]:
        key = (
            "pressure_window_cells",
            state.signature(),
            player,
            placements_available,
            self._config_cache_key(config),
        )
        cached = self._candidate_cache.get(key)
        if cached is not None:
            return [entry.cell for entry in cached]

        windows: list[tuple[int, int, tuple[Coord, ...]]] = []
        for summary in self._open_windows_for_player(state, config, player):
            if summary.empty_count <= placements_available:
                continue
            if summary.empty_count - placements_available > config.game.turn_placements:
                continue
            minimum_friendly = max(1, config.game.win_length - summary.empty_count)
            if summary.friendly_count < minimum_friendly:
                continue
            empties = tuple(sorted(cell for cell in summary.cells if state.is_empty(cell)))
            windows.append((summary.friendly_count, summary.empty_count, empties))

        windows.sort(key=lambda item: (-item[0], item[1], item[2]))
        ordered: list[Coord] = []
        seen: set[Coord] = set()
        for _friendly_count, _empty_count, empties in windows:
            for cell in empties:
                if cell in seen:
                    continue
                seen.add(cell)
                ordered.append(cell)
                if 0 < config.search.tactical_pressure_cell_cap <= len(ordered):
                    self._candidate_cache[key] = [SimpleNamespace(cell=item, total=float("inf")) for item in ordered]
                    return ordered

        self._candidate_cache[key] = [SimpleNamespace(cell=cell, total=float("inf")) for cell in ordered]
        return ordered

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
    def _is_remote_turn(
        state: GameState,
        cells: tuple[Coord, ...],
        config: AppConfig,
    ) -> bool:
        if not state.stones:
            return False
        center = state.suggested_center()
        remote_threshold = max(4, config.game.win_length - 2)
        return min(hex_distance(center, cell) for cell in cells) >= remote_threshold

    @staticmethod
    def _bounded_edge_bonus(
        cells: tuple[Coord, ...],
        config: AppConfig,
    ) -> int:
        bounds = config.game.bounds()
        if bounds is None or not cells:
            return 0
        min_q, max_q, min_r, max_r = bounds
        min_edge_distance = min(
            min(q - min_q, max_q - q, r - min_r, max_r - r)
            for q, r in cells
        )
        return max(0, config.game.win_length - min_edge_distance)

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

    @staticmethod
    def _state_for_player_turn(
        state: GameState,
        player: Player,
        placements_available: int,
    ) -> GameState:
        return GameState(
            stones=dict(state.stones),
            to_play=player,
            placements_remaining=placements_available,
            turn_index=state.turn_index,
            ply_count=state.ply_count,
            last_move=state.last_move,
            move_history=state.move_history,
        )
