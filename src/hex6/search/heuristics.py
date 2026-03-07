"""Heuristic evaluation helpers for shallow search."""

from __future__ import annotations

from dataclasses import dataclass

from hex6.config import AppConfig
from hex6.game import GameState, Player
from hex6.prototype.candidate_explorer import SparsePosition


@dataclass(frozen=True)
class HeuristicEvaluation:
    player: Player
    total: float
    friendly_windows: tuple[int, ...]
    enemy_windows: tuple[int, ...]
    live_cell_balance: int
    candidate_edge: float


def evaluate_state(state: GameState, config: AppConfig, player: Player | None = None) -> HeuristicEvaluation:
    player = player or state.to_play
    opponent: Player = "o" if player == "x" else "x"

    if state.winner == player:
        terminal = config.heuristic.terminal_score
        return HeuristicEvaluation(player, terminal, (), (), 0, 0.0)
    if state.winner == opponent:
        terminal = -config.heuristic.terminal_score
        return HeuristicEvaluation(player, terminal, (), (), 0, 0.0)

    position = SparsePosition.from_game_state(state)
    friendly_counts = _window_alignment_counts(position, config, player)
    enemy_counts = _window_alignment_counts(position, config, opponent)
    live = position.live_cells(config)
    live_cell_balance = len(live[player]) - len(live[opponent])

    friendly_score = _weighted_total(friendly_counts, config.heuristic.alignment_weights)
    enemy_score = _weighted_total(enemy_counts, config.heuristic.enemy_alignment_weights)

    candidate_edge = 0.0
    if config.heuristic.include_candidate_edge:
        friendly_candidates = position.top_first_stone_candidates(config, player)
        enemy_candidates = position.top_first_stone_candidates(config, opponent)
        candidate_edge = (friendly_candidates[0].total if friendly_candidates else 0.0) - (
            enemy_candidates[0].total if enemy_candidates else 0.0
        )

    total = (
        friendly_score
        - enemy_score
        + live_cell_balance * config.heuristic.live_cell_weight
        + candidate_edge * config.heuristic.candidate_score_weight
    )
    return HeuristicEvaluation(
        player=player,
        total=round(total, 3),
        friendly_windows=friendly_counts,
        enemy_windows=enemy_counts,
        live_cell_balance=live_cell_balance,
        candidate_edge=round(candidate_edge, 3),
    )


def _window_alignment_counts(
    position: SparsePosition,
    config: AppConfig,
    player: Player,
) -> tuple[int, ...]:
    counts = [0] * (config.game.win_length + 1)
    for summary in position.open_windows(config, player):
        capped = min(summary.friendly_count, config.game.win_length)
        counts[capped] += 1
    return tuple(counts)


def _weighted_total(counts: tuple[int, ...], weights: tuple[float, ...]) -> float:
    return sum(count * weights[index] for index, count in enumerate(counts))
