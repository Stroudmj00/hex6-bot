"""Immutable sparse game state for the Hex6 ruleset."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import Any, Literal, Sequence

from hex6.config.schema import GameConfig
from hex6.game.axial import Coord, LINE_AXES, add_coords, hex_distance, line_cells

Player = Literal["x", "o"]


class IllegalMoveError(ValueError):
    """Raised when a placement violates the current game state."""


@dataclass(frozen=True)
class MoveRecord:
    player: Player
    cell: Coord
    turn_index: int
    placements_remaining_after: int


@dataclass(frozen=True)
class GameState:
    """Sparse immutable game state.

    The rules layer is sparse by default and can optionally honor explicit configured bounds.
    """

    stones: dict[Coord, Player]
    to_play: Player
    placements_remaining: int
    turn_index: int
    ply_count: int
    winner: Player | None = None
    draw_reason: str | None = None
    winning_line: tuple[Coord, ...] | None = None
    last_move: Coord | None = None
    move_history: tuple[MoveRecord, ...] = ()

    @classmethod
    def initial(cls, game_config: GameConfig) -> "GameState":
        initial_state = cls(
            stones={},
            to_play=game_config.players[0],
            placements_remaining=game_config.opening_placements,
            turn_index=1,
            ply_count=0,
            last_move=None,
        )
        return initial_state._with_exhaustion_draw_if_needed(game_config)

    @cached_property
    def occupied(self) -> tuple[Coord, ...]:
        return tuple(self.stones.keys())

    @property
    def is_terminal(self) -> bool:
        return self.winner is not None or self.draw_reason is not None

    def signature(self) -> tuple[Any, ...]:
        return self._signature

    @cached_property
    def _signature(self) -> tuple[Any, ...]:
        return (
            tuple(sorted(self.stones.items())),
            self.to_play,
            self.placements_remaining,
            self.turn_index,
            self.ply_count,
            self.winner,
            self.draw_reason,
        )

    def opponent(self, player: Player | None = None) -> Player:
        player = player or self.to_play
        return "o" if player == "x" else "x"

    def is_empty(self, cell: Coord) -> bool:
        return cell not in self.stones

    def is_legal_placement(self, cell: Coord, game_config: GameConfig | None = None) -> bool:
        return (
            not self.is_terminal
            and self.is_empty(cell)
            and (game_config is None or game_config.is_in_bounds(cell))
        )

    @cached_property
    def _occupied_bounds(self) -> tuple[int, int, int, int]:
        if not self.occupied:
            return 0, 0, 0, 0
        qs = [coord[0] for coord in self.occupied]
        rs = [coord[1] for coord in self.occupied]
        return min(qs), max(qs), min(rs), max(rs)

    def occupied_bounds(self) -> tuple[int, int, int, int]:
        return self._occupied_bounds

    def suggested_center(self) -> Coord:
        min_q, max_q, min_r, max_r = self.occupied_bounds()
        return round((min_q + max_q) / 2), round((min_r + max_r) / 2)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "stones": [
                {"q": q, "r": r, "player": player}
                for (q, r), player in sorted(self.stones.items())
            ],
            "to_play": self.to_play,
            "placements_remaining": self.placements_remaining,
            "turn_index": self.turn_index,
            "ply_count": self.ply_count,
            "winner": self.winner,
            "draw_reason": self.draw_reason,
            "is_terminal": self.is_terminal,
            "winning_line": (
                [{"q": q, "r": r} for q, r in self.winning_line]
                if self.winning_line is not None
                else None
            ),
        }

    def remaining_empty_cells(self, game_config: GameConfig) -> int | None:
        bounds = game_config.bounds()
        if bounds is None:
            return None
        min_q, max_q, min_r, max_r = bounds
        total_cells = (max_q - min_q + 1) * (max_r - min_r + 1)
        return max(0, total_cells - len(self.stones))

    def can_complete_turn(self, game_config: GameConfig) -> bool:
        remaining = self.remaining_empty_cells(game_config)
        if remaining is None:
            return True
        return remaining >= self.placements_remaining

    def apply_turn(
        self,
        cells: Sequence[Coord],
        game_config: GameConfig,
        *,
        record_history: bool = True,
    ) -> "GameState":
        if len(cells) == 0 or len(cells) > self.placements_remaining:
            raise IllegalMoveError(
                f"expected {self.placements_remaining} placements, received {len(cells)}"
            )

        state = self
        for index, cell in enumerate(cells):
            state = state.apply_placement(cell, game_config, record_history=record_history)
            if state.is_terminal and index != len(cells) - 1:
                raise IllegalMoveError("turn continued after the game ended")
            if state.is_terminal:
                return state
        if len(cells) != self.placements_remaining:
            raise IllegalMoveError(
                f"expected {self.placements_remaining} placements, received {len(cells)}"
            )
        return state

    def apply_placement(
        self,
        cell: Coord,
        game_config: GameConfig,
        *,
        record_history: bool = True,
    ) -> "GameState":
        if self.is_terminal:
            raise IllegalMoveError("cannot place a stone after the game is over")
        if not game_config.is_in_bounds(cell):
            raise IllegalMoveError(f"cell {cell} is outside the configured board bounds")
        if not self.is_empty(cell):
            raise IllegalMoveError(f"cell {cell} is already occupied")

        player = self.to_play
        stones = dict(self.stones)
        stones[cell] = player
        ply_count = self.ply_count + 1
        winning_line = self.find_winning_line(stones, cell, player, game_config.win_length)
        remaining_after_move = self.placements_remaining - 1
        move_history = self.move_history
        if record_history:
            move_record = MoveRecord(
                player=player,
                cell=cell,
                turn_index=self.turn_index,
                placements_remaining_after=max(0, remaining_after_move),
            )
            move_history = self.move_history + (move_record,)

        if winning_line is not None:
            return GameState(
                stones=stones,
                to_play=player,
                placements_remaining=0,
                turn_index=self.turn_index,
                ply_count=ply_count,
                winner=player,
                draw_reason=None,
                winning_line=winning_line,
                last_move=cell,
                move_history=move_history,
            )

        if remaining_after_move > 0:
            return GameState(
                stones=stones,
                to_play=player,
                placements_remaining=remaining_after_move,
                turn_index=self.turn_index,
                ply_count=ply_count,
                last_move=cell,
                move_history=move_history,
            )._with_exhaustion_draw_if_needed(game_config)

        next_player = self.opponent(player)
        return GameState(
            stones=stones,
            to_play=next_player,
            placements_remaining=game_config.turn_placements,
            turn_index=self.turn_index + 1,
            ply_count=ply_count,
            last_move=cell,
            move_history=move_history,
        )._with_exhaustion_draw_if_needed(game_config)

    def _with_exhaustion_draw_if_needed(self, game_config: GameConfig) -> "GameState":
        if self.is_terminal or self.can_complete_turn(game_config):
            return self
        return GameState(
            stones=self.stones,
            to_play=self.to_play,
            placements_remaining=0,
            turn_index=self.turn_index,
            ply_count=self.ply_count,
            winner=None,
            draw_reason="board_exhausted",
            winning_line=None,
            last_move=self.last_move,
            move_history=self.move_history,
        )

    @staticmethod
    def find_winning_line(
        stones: dict[Coord, Player],
        cell: Coord,
        player: Player,
        win_length: int,
    ) -> tuple[Coord, ...] | None:
        for axis in LINE_AXES:
            line = GameState.contiguous_line(stones, cell, player, axis)
            if len(line) >= win_length:
                return line
        return None

    @staticmethod
    def contiguous_line(
        stones: dict[Coord, Player],
        origin: Coord,
        player: Player,
        axis: Coord,
    ) -> tuple[Coord, ...]:
        backward = GameState._walk(stones, origin, player, (-axis[0], -axis[1]))
        forward = GameState._walk(stones, origin, player, axis)
        start = backward[-1] if backward else origin
        end = forward[-1] if forward else origin

        full_length = hex_distance(start, end) + 1
        return line_cells(start, axis, full_length)

    @staticmethod
    def _walk(
        stones: dict[Coord, Player],
        origin: Coord,
        player: Player,
        direction: Coord,
    ) -> tuple[Coord, ...]:
        cells: list[Coord] = []
        current = add_coords(origin, direction)
        while stones.get(current) == player:
            cells.append(current)
            current = add_coords(current, direction)
        return tuple(cells)
