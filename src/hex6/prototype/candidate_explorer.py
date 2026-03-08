"""Prototype candidate-generation logic for the Hex6 ruleset.

This is intentionally exploratory rather than optimized. The goal is to keep the concepts
importable and configurable while we learn more about the game.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Literal

from hex6.config import AppConfig
from hex6.game.axial import (
    AXIAL_DIRECTIONS,
    Coord,
    add_coords,
    hex_distance,
    line_cells,
    min_distance_to_any,
)
from hex6.game.state import GameState

Player = Literal["x", "o"]


@lru_cache(maxsize=512)
def _windows_for_bounds(
    min_q: int,
    max_q: int,
    min_r: int,
    max_r: int,
    win_length: int,
) -> tuple[tuple[Coord, ...], ...]:
    windows: list[tuple[Coord, ...]] = []
    q_limit = max_q - win_length + 1
    r_limit = max_r - win_length + 1
    diagonal_min_r = min_r + win_length - 1

    for q in range(min_q, q_limit + 1):
        for r in range(min_r, max_r + 1):
            windows.append(line_cells((q, r), (1, 0), win_length))

    for q in range(min_q, max_q + 1):
        for r in range(min_r, r_limit + 1):
            windows.append(line_cells((q, r), (0, 1), win_length))

    for q in range(min_q, q_limit + 1):
        for r in range(diagonal_min_r, max_r + 1):
            windows.append(line_cells((q, r), (1, -1), win_length))

    return tuple(windows)


@dataclass(frozen=True)
class WindowSummary:
    cells: tuple[Coord, ...]
    friendly_count: int
    enemy_count: int
    empty_count: int


@dataclass(frozen=True)
class CandidateScore:
    cell: Coord
    frontier_contacts: int
    friendly_open_windows: int
    enemy_open_windows: int
    best_friendly_alignment: int
    best_enemy_alignment: int
    friendly_pressure: float
    enemy_pressure: float
    intersection_count: int
    island_bonus: float
    space_bonus: float
    total: float


@dataclass(frozen=True)
class SparsePosition:
    stones: dict[Coord, Player]
    to_play: Player = "x"
    placements_remaining: int = 2

    @classmethod
    def from_game_state(cls, state: GameState) -> "SparsePosition":
        return cls(
            stones=dict(state.stones),
            to_play=state.to_play,
            placements_remaining=state.placements_remaining,
        )

    @property
    def occupied(self) -> tuple[Coord, ...]:
        return tuple(self.stones.keys())

    def opponent(self, player: Player) -> Player:
        return "o" if player == "x" else "x"

    def empty(self, cell: Coord) -> bool:
        return cell not in self.stones

    def occupied_bounds(self) -> tuple[int, int, int, int]:
        if not self.stones:
            return 0, 0, 0, 0
        qs = [cell[0] for cell in self.stones]
        rs = [cell[1] for cell in self.stones]
        return min(qs), max(qs), min(rs), max(rs)

    def analysis_cells(self, config: AppConfig) -> set[Coord]:
        min_q, max_q, min_r, max_r = self.occupied_bounds()
        margin = config.prototype.outer_search_margin
        if not self.stones:
            origin_margin = max(config.prototype.analysis_margin, config.game.win_length)
            return {
                (q, r)
                for q in range(-origin_margin, origin_margin + 1)
                for r in range(-origin_margin, origin_margin + 1)
            }

        return {
            (q, r)
            for q in range(min_q - margin, max_q + margin + 1)
            for r in range(min_r - margin, max_r + margin + 1)
        }

    def windows_in_scope(self, config: AppConfig) -> tuple[tuple[Coord, ...], ...]:
        if not self.stones:
            origin_margin = max(config.prototype.analysis_margin, config.game.win_length)
            return _windows_for_bounds(
                -origin_margin,
                origin_margin,
                -origin_margin,
                origin_margin,
                config.game.win_length,
            )

        min_q, max_q, min_r, max_r = self.occupied_bounds()
        margin = config.prototype.outer_search_margin
        return _windows_for_bounds(
            min_q - margin,
            max_q + margin,
            min_r - margin,
            max_r + margin,
            config.game.win_length,
        )

    def summarize_window(self, window: tuple[Coord, ...], player: Player) -> WindowSummary:
        opponent = self.opponent(player)
        friendly_count = sum(1 for cell in window if self.stones.get(cell) == player)
        enemy_count = sum(1 for cell in window if self.stones.get(cell) == opponent)
        empty_count = len(window) - friendly_count - enemy_count
        return WindowSummary(window, friendly_count, enemy_count, empty_count)

    def open_windows(self, config: AppConfig, player: Player) -> list[WindowSummary]:
        return self.open_windows_from_scope(self.windows_in_scope(config), player)

    def open_windows_from_scope(
        self,
        windows: Iterable[tuple[Coord, ...]],
        player: Player,
    ) -> list[WindowSummary]:
        windows = tuple(windows)
        return [
            summary
            for summary in (self.summarize_window(window, player) for window in windows)
            if summary.enemy_count == 0
        ]

    def live_cells(self, config: AppConfig) -> dict[Player, set[Coord]]:
        windows = self.windows_in_scope(config)
        return self.live_cells_from_windows(windows)

    def live_cells_from_windows(self, windows: Iterable[tuple[Coord, ...]]) -> dict[Player, set[Coord]]:
        windows = tuple(windows)
        live: dict[Player, set[Coord]] = {"x": set(), "o": set()}
        for player in ("x", "o"):
            for window in self.open_windows_from_scope(windows, player):
                live[player].update(cell for cell in window.cells if self.empty(cell))
        return live

    def globally_dead_cells(self, config: AppConfig) -> set[Coord]:
        live = self.live_cells(config)
        empty_cells = {cell for cell in self.analysis_cells(config) if self.empty(cell)}
        return empty_cells - live["x"] - live["o"]

    def frontier_cells(self, distance: int) -> set[Coord]:
        if not self.stones:
            return {(0, 0)}

        frontier: set[Coord] = set()
        for cell in self.analysis_cells_for_occupied(distance):
            if self.empty(cell):
                frontier.add(cell)
        return frontier

    def analysis_cells_for_occupied(self, distance: int) -> set[Coord]:
        expanded: set[Coord] = set()
        for origin in self.occupied:
            for dq in range(-distance, distance + 1):
                for dr in range(-distance, distance + 1):
                    candidate = (origin[0] + dq, origin[1] + dr)
                    if hex_distance(origin, candidate) <= distance:
                        expanded.add(candidate)
        return expanded

    def candidate_scores(self, config: AppConfig, player: Player | None = None) -> list[CandidateScore]:
        player = player or self.to_play
        opponent = self.opponent(player)
        windows = tuple(self.windows_in_scope(config))
        analysis_cells = self.analysis_cells(config)
        empty_cells = {cell for cell in analysis_cells if self.empty(cell)}

        player_counts = self._open_window_features(windows, player, empty_cells, config.heuristic.alignment_weights)
        opponent_counts = self._open_window_features(
            windows,
            opponent,
            empty_cells,
            config.heuristic.enemy_alignment_weights,
        )
        live = {
            player: set(player_counts["open_windows"]),
            opponent: set(opponent_counts["open_windows"]),
        }
        dead = (
            empty_cells - live["x"] - live["o"]
            if config.prototype.prune_globally_dead_cells
            else set()
        )
        frontier = self.frontier_cells(config.prototype.frontier_distance)

        if not self.stones:
            candidates = set(frontier)
        else:
            candidates = set(frontier)
            candidates.update(live[player])
            candidates.update(live[opponent])
            candidates = {cell for cell in candidates if cell not in dead}

        if config.prototype.allow_long_range_islands and self.occupied:
            candidates.update(
                self.island_cells(
                    config,
                    player,
                    windows=windows,
                    live=live,
                )
            )

        scored: list[CandidateScore] = []
        occupied = self.occupied
        occupied_set = set(occupied)
        frontier_contacts = self._frontier_contact_counts(candidates, occupied_set)
        neighbor_counts = self._neighbor_counts_for_space(candidates, occupied_set)

        for cell in sorted(candidates):
            friendly_window_count = player_counts["counts"].get(cell, 0)
            enemy_window_count = opponent_counts["counts"].get(cell, 0)
            best_friendly_alignment = player_counts["best_alignment"].get(cell, 0)
            best_enemy_alignment = opponent_counts["best_alignment"].get(cell, 0)
            friendly_pressure = player_counts["pressure"].get(cell, 0.0)
            enemy_pressure = opponent_counts["pressure"].get(cell, 0.0)
            intersection_count = friendly_window_count + enemy_window_count
            island_bonus = self.island_bonus(config, cell, occupied)
            space_bonus = float(max(0.0, 4.0 - neighbor_counts.get(cell, 0)))
            total = (
                frontier_contacts.get(cell, 0) * config.scoring.frontier
                + friendly_window_count * config.scoring.friendly_open_window
                + enemy_window_count * config.scoring.enemy_open_window
                + best_friendly_alignment * config.scoring.friendly_alignment
                + best_enemy_alignment * config.scoring.enemy_alignment
                + friendly_pressure
                + enemy_pressure
                + intersection_count * config.scoring.intersection
                + island_bonus * config.scoring.island
                + space_bonus * config.scoring.space
            )
            scored.append(
                CandidateScore(
                    cell=cell,
                    frontier_contacts=frontier_contacts.get(cell, 0),
                    friendly_open_windows=friendly_window_count,
                    enemy_open_windows=enemy_window_count,
                    best_friendly_alignment=best_friendly_alignment,
                    best_enemy_alignment=best_enemy_alignment,
                    friendly_pressure=round(friendly_pressure, 3),
                    enemy_pressure=round(enemy_pressure, 3),
                    intersection_count=intersection_count,
                    island_bonus=island_bonus,
                    space_bonus=space_bonus,
                    total=round(total, 3),
                )
            )

        scored.sort(key=lambda score: score.total, reverse=True)
        return scored

    def _open_window_features(
        self,
        windows: Iterable[tuple[Coord, ...]],
        player: Player,
        empty_cells: set[Coord],
        alignment_weights: tuple[float, ...],
    ) -> dict[str, dict[Coord, float] | dict[Coord, int] | set[Coord]]:
        windows = tuple(windows)
        counts: dict[Coord, int] = {}
        best_alignment: dict[Coord, int] = {}
        pressure: dict[Coord, float] = {}
        open_windows: set[Coord] = set()

        for window in windows:
            summary = self.summarize_window(window, player)
            if summary.enemy_count != 0:
                continue
            weight = alignment_weights[summary.friendly_count]
            for cell in summary.cells:
                if cell not in empty_cells:
                    continue
                counts[cell] = counts.get(cell, 0) + 1
                best_alignment[cell] = max(best_alignment.get(cell, 0), summary.friendly_count)
                pressure[cell] = pressure.get(cell, 0.0) + weight
                open_windows.add(cell)

        return {
            "counts": counts,
            "best_alignment": best_alignment,
            "pressure": pressure,
            "open_windows": open_windows,
        }

    def _frontier_contact_counts(self, candidates: set[Coord], occupied: set[Coord]) -> dict[Coord, int]:
        if not candidates or not occupied:
            return {}

        contacts: dict[Coord, int] = {cell: 0 for cell in candidates}
        for occupied_cell in occupied:
            for direction in AXIAL_DIRECTIONS:
                candidate = add_coords(occupied_cell, direction)
                if candidate in contacts:
                    contacts[candidate] += 1
        return contacts

    def _neighbor_counts_for_space(self, candidates: set[Coord], occupied: Iterable[Coord]) -> dict[Coord, int]:
        if not candidates:
            return {}

        neighbor_counts: dict[Coord, int] = {cell: 0 for cell in candidates}
        occupied_cells = tuple(occupied)
        if not occupied_cells:
            return neighbor_counts

        for candidate in neighbor_counts:
            count = 0
            for other in occupied_cells:
                if other != candidate and hex_distance(other, candidate) <= 2:
                    count += 1
            neighbor_counts[candidate] = count
        return neighbor_counts

    def top_first_stone_candidates(self, config: AppConfig, player: Player | None = None) -> list[CandidateScore]:
        return self.candidate_scores(config, player)[: config.prototype.first_stone_candidate_limit]

    def island_cells(
        self,
        config: AppConfig,
        player: Player,
        windows: Iterable[tuple[Coord, ...]] | None = None,
        live: dict[Player, set[Coord]] | None = None,
    ) -> set[Coord]:
        opponent = self.opponent(player)
        windows = tuple(windows or self.windows_in_scope(config))
        live = live or self.live_cells_from_windows(windows)
        player_live = live[player]
        opponent_live = live[opponent]
        candidate_pool = self.analysis_cells(config) - set(self.occupied)
        island_cells: set[Coord] = set()
        open_window_count: dict[Coord, int] = {}

        for window in windows:
            summary = self.summarize_window(window, player)
            if summary.enemy_count != 0:
                continue
            for cell in summary.cells:
                if self.empty(cell):
                    open_window_count[cell] = open_window_count.get(cell, 0) + 1

        for cell in candidate_pool:
            if self.occupied:
                distance = min_distance_to_any(cell, self.occupied)
            else:
                distance = 0

            if not (config.prototype.island_min_distance <= distance <= config.prototype.island_max_distance):
                continue

            if open_window_count.get(cell, 0) < config.prototype.min_open_windows_for_island:
                continue

            if cell in player_live or cell in opponent_live:
                island_cells.add(cell)

        return island_cells

    def frontier_contact_count(self, cell: Coord) -> int:
        return sum(1 for occupied in self.occupied if hex_distance(cell, occupied) <= 1)

    def island_bonus(self, config: AppConfig, cell: Coord, occupied: Iterable[Coord]) -> float:
        occupied_list = tuple(occupied)
        if not occupied_list:
            return 0.0

        distance = min_distance_to_any(cell, occupied_list)
        if config.prototype.island_min_distance <= distance <= config.prototype.island_max_distance:
            return 1.0
        return 0.0

    def space_bonus(self, config: AppConfig, cell: Coord) -> float:
        # Favor cells with some room around them while avoiding extremely isolated noise.
        neighbor_count = sum(
            1
            for other in self.analysis_cells_for_occupied(config.prototype.frontier_distance + 1)
            if other != cell and hex_distance(cell, other) <= 2 and other in self.stones
        )
        return max(0.0, 4.0 - neighbor_count)
