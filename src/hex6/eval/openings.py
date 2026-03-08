"""Opening suite helpers for arena evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib

from hex6.config import AppConfig
from hex6.game import Coord, GameState, IllegalMoveError


@dataclass(frozen=True)
class OpeningScenario:
    name: str
    description: str
    placements: tuple[Coord, ...]
    state: GameState


def load_opening_suite(path: str | Path, config: AppConfig) -> list[OpeningScenario]:
    suite_path = Path(path)
    with suite_path.open("rb") as handle:
        data = tomllib.load(handle)

    scenarios: list[OpeningScenario] = []
    for entry in data["scenarios"]:
        placements = tuple((int(item[0]), int(item[1])) for item in entry["placements"])
        state = build_state_from_placements(placements, config)
        expected_to_play = entry.get("expected_to_play")
        expected_remaining = entry.get("expected_placements_remaining")
        if expected_to_play is not None and state.to_play != expected_to_play:
            raise IllegalMoveError(
                f"opening {entry['name']} expected to_play={expected_to_play}, got {state.to_play}"
            )
        if expected_remaining is not None and state.placements_remaining != int(expected_remaining):
            raise IllegalMoveError(
                "opening "
                f"{entry['name']} expected placements_remaining={expected_remaining}, "
                f"got {state.placements_remaining}"
            )

        scenarios.append(
            OpeningScenario(
                name=str(entry["name"]),
                description=str(entry.get("description", "")),
                placements=placements,
                state=state,
            )
        )
    return scenarios


def build_state_from_placements(placements: tuple[Coord, ...], config: AppConfig) -> GameState:
    state = GameState.initial(config.game)
    for cell in placements:
        state = state.apply_placement(cell, config.game)
        if state.is_terminal:
            raise IllegalMoveError("opening suite contains a terminal position")
    return state
