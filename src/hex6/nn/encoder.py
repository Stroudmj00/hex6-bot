"""Tensor encoding helpers for sparse Hex6 positions."""

from __future__ import annotations

from dataclasses import dataclass

import torch

from hex6.config import AppConfig
from hex6.game import Coord, GameState, Player


@dataclass(frozen=True)
class EncodedPosition:
    tensor: torch.Tensor
    center: Coord
    radius: int
    index_to_cell: tuple[Coord, ...]


def encode_state(
    state: GameState,
    config: AppConfig,
    perspective: Player | None = None,
) -> EncodedPosition:
    perspective = perspective or state.to_play
    opponent: Player = "o" if perspective == "x" else "x"
    radius = config.model.board_crop_radius
    side = radius * 2 + 1
    center = crop_center(state)

    tensor = torch.zeros((6, side, side), dtype=torch.float32)
    index_to_cell: list[Coord] = []

    last_move = state.move_history[-1].cell if state.move_history else None
    placement_fill = state.placements_remaining / max(1, config.game.turn_placements)

    for row, r in enumerate(range(center[1] - radius, center[1] + radius + 1)):
        for col, q in enumerate(range(center[0] - radius, center[0] + radius + 1)):
            cell = (q, r)
            index_to_cell.append(cell)
            occupant = state.stones.get(cell)
            if occupant == perspective:
                tensor[0, row, col] = 1.0
            elif occupant == opponent:
                tensor[1, row, col] = 1.0

            if last_move == cell:
                tensor[2, row, col] = 1.0

            tensor[3, row, col] = 1.0
            tensor[4, row, col] = 1.0 if perspective == "x" else 0.0
            tensor[5, row, col] = placement_fill

    return EncodedPosition(
        tensor=tensor,
        center=center,
        radius=radius,
        index_to_cell=tuple(index_to_cell),
    )


def crop_center(state: GameState) -> Coord:
    if not state.stones:
        return 0, 0

    qs = [cell[0] for cell in state.stones]
    rs = [cell[1] for cell in state.stones]
    center_q = round((min(qs) + max(qs)) / 2)
    center_r = round((min(rs) + max(rs)) / 2)
    return center_q, center_r


def cell_to_policy_index(encoded: EncodedPosition, cell: Coord) -> int | None:
    try:
        return encoded.index_to_cell.index(cell)
    except ValueError:
        return None

