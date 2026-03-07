"""Prototype candidate-generation logic for the Hex6 ruleset.

This is intentionally exploratory rather than optimized. The goal is to keep the concepts
importable and configurable while we learn more about the game.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from hex6.config import AppConfig
from hex6.game.axial import LINE_AXES, Coord, hex_distance, line_cells, min_distance_to_any
from hex6.game.state import GameState

Player = Literal["x", "o"]


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

    def windows_in_scope(self, config: AppConfig) -> list[tuple[Coord, ...]]:
        cells = self.analysis_cells(config)
        min_q = min(cell[0] for cell in cells)
        max_q = max(cell[0] for cell in cells)
        min_r = min(cell[1] for cell in cells)
        max_r = max(cell[1] for cell in cells)
        windows: list[tuple[Coord, ...]] = []
        win_length = config.game.win_length

        for direction in LINE_AXES:
            for q in range(min_q, max_q + 1):
                for r in range(min_r, max_r + 1):
                    start = (q, r)
                    window = line_cells(start, direction, win_length)
                    if all(cell in cells for cell in window):
                        windows.append(window)

        return windows

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
        windows = self.windows_in_scope(config)
        player_windows = self.open_windows_from_scope(windows, player)
        opponent_windows = self.open_windows_from_scope(windows, opponent)
        live = self.live_cells_from_windows(windows)
        dead = (
            {cell for cell in self.analysis_cells(config) if self.empty(cell)} - live["x"] - live["o"]
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

        for cell in sorted(candidates):
            frontier_contacts = self.frontier_contact_count(cell)
            friendly_windows = [window for window in player_windows if cell in window.cells]
            enemy_windows = [window for window in opponent_windows if cell in window.cells]
            best_friendly_alignment = max((window.friendly_count for window in friendly_windows), default=0)
            best_enemy_alignment = max((window.friendly_count for window in enemy_windows), default=0)
            friendly_pressure = sum(
                config.heuristic.alignment_weights[window.friendly_count] for window in friendly_windows
            )
            enemy_pressure = sum(
                config.heuristic.enemy_alignment_weights[window.friendly_count] for window in enemy_windows
            )
            intersection_count = len(friendly_windows) + len(enemy_windows)
            island_bonus = self.island_bonus(config, cell, occupied)
            space_bonus = self.space_bonus(config, cell)
            total = (
                frontier_contacts * config.scoring.frontier
                + len(friendly_windows) * config.scoring.friendly_open_window
                + len(enemy_windows) * config.scoring.enemy_open_window
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
                    frontier_contacts=frontier_contacts,
                    friendly_open_windows=len(friendly_windows),
                    enemy_open_windows=len(enemy_windows),
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
