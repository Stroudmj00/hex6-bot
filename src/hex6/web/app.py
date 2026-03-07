"""Flask app for local interactive play."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, render_template, request

from hex6.config import AppConfig, load_config
from hex6.game import GameState, IllegalMoveError, Player
from hex6.game.axial import Coord, hex_disc, hex_distance
from hex6.search import BaselineTurnSearch


@dataclass
class SessionState:
    human_player: Player
    bot_player: Player
    state: GameState
    last_bot_turn: tuple[Coord, ...] = ()


def create_app(config_path: str = "configs/play.toml") -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).with_name("templates")),
        static_folder=str(Path(__file__).with_name("static")),
    )
    config = load_config(config_path)
    search = BaselineTurnSearch()
    sessions: dict[str, SessionState] = {}

    @app.get("/")
    def index() -> str:
        return render_template("index.html", config_path=config_path)

    @app.post("/api/new-game")
    def new_game():
        payload = request.get_json(silent=True) or {}
        human_raw = str(payload.get("human", "x")).lower()
        human_player: Player = "o" if human_raw == "o" else "x"
        bot_player: Player = "o" if human_player == "x" else "x"
        session_id = str(uuid4())
        state = GameState.initial(config.game)
        last_bot_turn: tuple[Coord, ...] = ()

        if state.to_play == bot_player:
            bot_turn = search.choose_turn(state, config)
            state = search.apply_cells(state, bot_turn.cells, config)
            last_bot_turn = bot_turn.cells

        sessions[session_id] = SessionState(
            human_player=human_player,
            bot_player=bot_player,
            state=state,
            last_bot_turn=last_bot_turn,
        )
        return jsonify(_session_payload(session_id, sessions[session_id], config))

    @app.get("/api/state/<session_id>")
    def get_state(session_id: str):
        session = sessions.get(session_id)
        if session is None:
            return jsonify({"error": "unknown_session"}), 404
        return jsonify(_session_payload(session_id, session, config))

    @app.post("/api/play/<session_id>")
    def play(session_id: str):
        session = sessions.get(session_id)
        if session is None:
            return jsonify({"error": "unknown_session"}), 404

        payload = request.get_json(silent=True) or {}
        cells = payload.get("cells", [])
        move_cells = tuple((int(cell["q"]), int(cell["r"])) for cell in cells)

        try:
            session.state = _apply_human_move(session, move_cells, config)
            session.last_bot_turn = ()
            if not session.state.is_terminal and session.state.to_play == session.bot_player:
                bot_turn = search.choose_turn(session.state, config)
                session.state = search.apply_cells(session.state, bot_turn.cells, config)
                session.last_bot_turn = bot_turn.cells
        except IllegalMoveError as exc:
            return jsonify({"error": "illegal_move", "message": str(exc)}), 400

        return jsonify(_session_payload(session_id, session, config))

    return app


def _apply_human_move(
    session: SessionState,
    cells: tuple[Coord, ...],
    config: AppConfig,
) -> GameState:
    state = session.state
    if state.is_terminal:
        raise IllegalMoveError("game is already over")
    if state.to_play != session.human_player:
        raise IllegalMoveError("it is not the human player's turn")
    if len(cells) != state.placements_remaining:
        raise IllegalMoveError(
            f"expected {state.placements_remaining} placements, received {len(cells)}"
        )
    return state.apply_turn(cells, config.game)


def _session_payload(session_id: str, session: SessionState, config: AppConfig) -> dict[str, object]:
    state = session.state
    center = state.suggested_center()
    radius = _suggested_radius(state, center)
    visible_cells = [
        {"q": q, "r": r, "occupied": not state.is_empty((q, r))}
        for q, r in sorted(hex_disc(center, radius), key=lambda item: (item[1], item[0]))
    ]
    return {
        "session_id": session_id,
        "human_player": session.human_player,
        "bot_player": session.bot_player,
        "state": state.to_mapping(),
        "last_bot_turn": [{"q": q, "r": r} for q, r in session.last_bot_turn],
        "view": {
            "center": {"q": center[0], "r": center[1]},
            "radius": radius,
            "cells": visible_cells,
        },
        "config": {
            "win_length": config.game.win_length,
            "opening_placements": config.game.opening_placements,
            "turn_placements": config.game.turn_placements,
        },
    }


def _suggested_radius(state: GameState, center: Coord) -> int:
    if not state.stones:
        return 4
    max_distance = max(hex_distance(cell, center) for cell in state.stones)
    return max(4, min(8, max_distance + 2))
