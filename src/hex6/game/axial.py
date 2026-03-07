"""Axial-coordinate helpers for hex-grid logic."""

from __future__ import annotations

from typing import Iterable

Coord = tuple[int, int]

AXIAL_DIRECTIONS: tuple[Coord, ...] = (
    (1, 0),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (0, -1),
    (1, -1),
)

LINE_AXES: tuple[Coord, ...] = (
    (1, 0),
    (0, 1),
    (1, -1),
)


def add_coords(a: Coord, b: Coord) -> Coord:
    return a[0] + b[0], a[1] + b[1]


def scale(coord: Coord, factor: int) -> Coord:
    return coord[0] * factor, coord[1] * factor


def neighbors(coord: Coord) -> tuple[Coord, ...]:
    return tuple(add_coords(coord, direction) for direction in AXIAL_DIRECTIONS)


def hex_distance(a: Coord, b: Coord) -> int:
    aq, ar = a
    bq, br = b
    dq = aq - bq
    dr = ar - br
    ds = (-aq - ar) - (-bq - br)
    return max(abs(dq), abs(dr), abs(ds))


def line_cells(start: Coord, direction: Coord, length: int) -> tuple[Coord, ...]:
    return tuple(add_coords(start, scale(direction, offset)) for offset in range(length))


def min_distance_to_any(cell: Coord, others: Iterable[Coord]) -> int:
    return min(hex_distance(cell, other) for other in others)

