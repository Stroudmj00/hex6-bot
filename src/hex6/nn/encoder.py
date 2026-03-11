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
    tensor[3].fill_(1.0)
    tensor[4].fill_(1.0 if perspective == "x" else 0.0)
    tensor[5].fill_(state.placements_remaining / max(1, config.game.turn_placements))

    last_move = state.last_move if state.last_move is not None else (state.move_history[-1].cell if state.move_history else None)
    min_q = center[0] - radius
    min_r = center[1] - radius

    for (q, r), occupant in state.stones.items():
        col = q - min_q
        row = r - min_r
        if row < 0 or row >= side or col < 0 or col >= side:
            continue
        if occupant == perspective:
            tensor[0, row, col] = 1.0
        elif occupant == opponent:
            tensor[1, row, col] = 1.0

    if last_move is not None:
        col = last_move[0] - min_q
        row = last_move[1] - min_r
        if 0 <= row < side and 0 <= col < side:
            tensor[2, row, col] = 1.0

    index_to_cell = tuple(
        (q, r)
        for r in range(min_r, min_r + side)
        for q in range(min_q, min_q + side)
    )

    return EncodedPosition(
        tensor=tensor,
        center=center,
        radius=radius,
        index_to_cell=index_to_cell,
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
    return policy_index_for_cell(encoded.center, encoded.radius, cell)


def policy_index_for_cell(center: Coord, radius: int, cell: Coord) -> int | None:
    side = radius * 2 + 1
    min_q = center[0] - radius
    min_r = center[1] - radius
    col = cell[0] - min_q
    row = cell[1] - min_r
    if row < 0 or row >= side or col < 0 or col >= side:
        return None
    return (row * side) + col
