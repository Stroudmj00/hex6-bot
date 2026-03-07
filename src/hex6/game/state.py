"""Immutable sparse game state for the Hex6 ruleset."""

from __future__ import annotations

from dataclasses import dataclass
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

    The board is legally infinite. Search and model code can impose their own candidate
    restrictions, but the rules layer accepts any empty coordinate.
    """

    stones: dict[Coord, Player]
    to_play: Player
    placements_remaining: int
    turn_index: int
    ply_count: int
    winner: Player | None = None
    winning_line: tuple[Coord, ...] | None = None
    move_history: tuple[MoveRecord, ...] = ()

    @classmethod
    def initial(cls, game_config: GameConfig) -> "GameState":
        return cls(
            stones={},
            to_play=game_config.players[0],
            placements_remaining=game_config.opening_placements,
            turn_index=1,
            ply_count=0,
        )

    @property
    def occupied(self) -> tuple[Coord, ...]:
        return tuple(self.stones.keys())

    @property
    def is_terminal(self) -> bool:
        return self.winner is not None

    def signature(self) -> tuple[Any, ...]:
        return (
            tuple(sorted(self.stones.items())),
            self.to_play,
            self.placements_remaining,
            self.turn_index,
            self.ply_count,
            self.winner,
        )

    def opponent(self, player: Player | None = None) -> Player:
        player = player or self.to_play
        return "o" if player == "x" else "x"

    def is_empty(self, cell: Coord) -> bool:
        return cell not in self.stones

    def is_legal_placement(self, cell: Coord) -> bool:
        return not self.is_terminal and self.is_empty(cell)

    def occupied_bounds(self) -> tuple[int, int, int, int]:
        if not self.stones:
            return 0, 0, 0, 0
        qs = [coord[0] for coord in self.stones]
        rs = [coord[1] for coord in self.stones]
        return min(qs), max(qs), min(rs), max(rs)

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
            "winning_line": (
                [{"q": q, "r": r} for q, r in self.winning_line]
                if self.winning_line is not None
                else None
            ),
        }

    def apply_turn(self, cells: Sequence[Coord], game_config: GameConfig) -> "GameState":
        if len(cells) != self.placements_remaining:
            raise IllegalMoveError(
                f"expected {self.placements_remaining} placements, received {len(cells)}"
            )

        state = self
        for index, cell in enumerate(cells):
            state = state.apply_placement(cell, game_config)
            if state.is_terminal and index != len(cells) - 1:
                raise IllegalMoveError("turn continued after a winning placement")
        return state

    def apply_placement(self, cell: Coord, game_config: GameConfig) -> "GameState":
        if self.is_terminal:
            raise IllegalMoveError("cannot place a stone after the game is over")
        if not self.is_empty(cell):
            raise IllegalMoveError(f"cell {cell} is already occupied")

        player = self.to_play
        stones = dict(self.stones)
        stones[cell] = player
        ply_count = self.ply_count + 1
        winning_line = self.find_winning_line(stones, cell, player, game_config.win_length)
        remaining_after_move = self.placements_remaining - 1
        move_record = MoveRecord(
            player=player,
            cell=cell,
            turn_index=self.turn_index,
            placements_remaining_after=max(0, remaining_after_move),
        )

        if winning_line is not None:
            return GameState(
                stones=stones,
                to_play=player,
                placements_remaining=0,
                turn_index=self.turn_index,
                ply_count=ply_count,
                winner=player,
                winning_line=winning_line,
                move_history=self.move_history + (move_record,),
            )

        if remaining_after_move > 0:
            return GameState(
                stones=stones,
                to_play=player,
                placements_remaining=remaining_after_move,
                turn_index=self.turn_index,
                ply_count=ply_count,
                move_history=self.move_history + (move_record,),
            )

        next_player = self.opponent(player)
        return GameState(
            stones=stones,
            to_play=next_player,
            placements_remaining=game_config.turn_placements,
            turn_index=self.turn_index + 1,
            ply_count=ply_count,
            move_history=self.move_history + (move_record,),
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
