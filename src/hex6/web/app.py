"""Flask app for local interactive play."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, render_template, request

from hex6.config import AppConfig, load_config
from hex6.game import GameState, IllegalMoveError, Player
from hex6.game.axial import Coord
from hex6.search.baseline import BaselineTurnSearch


@dataclass
class SessionState:
    human_player: Player
    bot_player: Player
    state: GameState
    display_anchor: Coord | None = None
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
        display_anchor: Coord | None = None
        last_bot_turn: tuple[Coord, ...] = ()

        if state.to_play == bot_player:
            bot_turn = search.choose_turn(state, config)
            state = search.apply_cells(state, bot_turn.cells, config)
            if state.move_history:
                display_anchor = state.move_history[0].cell
            last_bot_turn = bot_turn.cells

        sessions[session_id] = SessionState(
            human_player=human_player,
            bot_player=bot_player,
            state=state,
            display_anchor=display_anchor,
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
            absolute_cells = _to_absolute_cells(session, move_cells)
            session.state = _apply_human_move(session, absolute_cells, config)
            if session.display_anchor is None and session.state.move_history:
                session.display_anchor = session.state.move_history[0].cell
            session.last_bot_turn = ()
            if not session.state.is_terminal and session.state.to_play == session.bot_player:
                bot_turn = search.choose_turn(session.state, config)
                session.state = search.apply_cells(session.state, bot_turn.cells, config)
                if session.display_anchor is None and session.state.move_history:
                    session.display_anchor = session.state.move_history[0].cell
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
    anchor = session.display_anchor or (0, 0)
    stones = [
        {"q": q - anchor[0], "r": r - anchor[1], "player": player}
        for (q, r), player in sorted(state.stones.items())
    ]
    winning_line = (
        [{"q": q - anchor[0], "r": r - anchor[1]} for q, r in state.winning_line]
        if state.winning_line is not None
        else None
    )
    last_bot_turn = [{"q": q - anchor[0], "r": r - anchor[1]} for q, r in session.last_bot_turn]
    suggested_center = state.suggested_center()
    return {
        "session_id": session_id,
        "human_player": session.human_player,
        "bot_player": session.bot_player,
        "state": {
            **state.to_mapping(),
            "stones": stones,
            "winning_line": winning_line,
        },
        "last_bot_turn": last_bot_turn,
        "view": {
            "anchor": {"q": anchor[0], "r": anchor[1]},
            "suggested_center": {
                "q": suggested_center[0] - anchor[0],
                "r": suggested_center[1] - anchor[1],
            },
        },
        "config": {
            "win_length": config.game.win_length,
            "opening_placements": config.game.opening_placements,
            "turn_placements": config.game.turn_placements,
        },
    }


def _to_absolute_cells(session: SessionState, relative_cells: tuple[Coord, ...]) -> tuple[Coord, ...]:
    anchor = session.display_anchor or (0, 0)
    return tuple((q + anchor[0], r + anchor[1]) for q, r in relative_cells)
