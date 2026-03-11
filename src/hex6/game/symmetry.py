"""Symmetry helpers for axial hex coordinates and sparse game states."""

from __future__ import annotations

from hex6.game.axial import Coord
from hex6.game.state import GameState, MoveRecord


def rotate_coord(coord: Coord, steps: int) -> Coord:
    """Rotate an axial coordinate by 60-degree steps around the origin."""

    x, z = coord
    y = -x - z
    steps %= 6
    for _ in range(steps):
        x, y, z = -z, -x, -y
    return x, z


def rotate_state(state: GameState, steps: int) -> GameState:
    if steps % 6 == 0:
        return state

    return GameState(
        stones={rotate_coord(cell, steps): player for cell, player in state.stones.items()},
        to_play=state.to_play,
        placements_remaining=state.placements_remaining,
        turn_index=state.turn_index,
        ply_count=state.ply_count,
        winner=state.winner,
        draw_reason=state.draw_reason,
        winning_line=(
            tuple(rotate_coord(cell, steps) for cell in state.winning_line)
            if state.winning_line is not None
            else None
        ),
        last_move=(rotate_coord(state.last_move, steps) if state.last_move is not None else None),
        move_history=tuple(
            MoveRecord(
                player=record.player,
                cell=rotate_coord(record.cell, steps),
                turn_index=record.turn_index,
                placements_remaining_after=record.placements_remaining_after,
            )
            for record in state.move_history
        ),
    )
