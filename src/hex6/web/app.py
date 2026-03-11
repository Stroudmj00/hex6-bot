"""Flask app for local interactive play."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, render_template, request

from hex6.config import AppConfig, load_config
from hex6.game import GameState, IllegalMoveError, Player
from hex6.game.axial import Coord
from hex6.search import BaselineTurnSearch, GuidedMctsTurnSearch, ModelGuidedTurnSearch


@dataclass
class SessionState:
    human_player: Player | None
    bot_search_by_player: dict[Player, object]
    bot_label_by_player: dict[Player, str]
    state: GameState
    display_anchor: Coord | None = None
    last_bot_turn: tuple[Coord, ...] = ()


def create_app(
    config_path: str = "configs/play.toml",
    checkpoint_path: str | None = None,
    spectator_opponent_checkpoint: str | None = None,
) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).with_name("templates")),
        static_folder=str(Path(__file__).with_name("static")),
    )
    config = load_config(config_path)
    primary_search, primary_label = _build_bot_search(config, checkpoint_path)
    opponent_search, opponent_label = _build_bot_search(config, spectator_opponent_checkpoint)
    sessions: dict[str, SessionState] = {}

    @app.get("/healthz")
    def healthz():
        return jsonify(
            {
                "ok": True,
                "config_path": config_path,
                "bot_label": primary_label,
                "board_mode": config.game.board_mode,
                "board_width": config.game.board_width,
                "board_height": config.game.board_height,
            }
        )

    @app.get("/")
    def index() -> str:
        board_bounds = config.game.bounds()
        board_title = "Infinite Grid" if board_bounds is None else f"{config.game.board_width} x {config.game.board_height} Board"
        board_lede = (
            "Infinite-board rules, cropped local view"
            if board_bounds is None
            else "Bounded-board rules, clipped local view"
        )
        return render_template(
            "index.html",
            config_path=config_path,
            config_name=Path(config_path).name,
            bot_label=primary_label,
            board_title=board_title,
            board_lede=board_lede,
            board_caption=(
                f"Opening turn places {config.game.opening_placements} "
                f"{_pluralize('stone', config.game.opening_placements)}, then each turn places "
                f"{config.game.turn_placements} {_pluralize('stone', config.game.turn_placements)}. "
                f"First line of {config.game.win_length} wins."
            ),
            bootstrap_payload=_web_bootstrap_payload(
                config_path=config_path,
                config=config,
                bot_label=primary_label,
                board_title=board_title,
                board_lede=board_lede,
            ),
        )

    @app.post("/api/new-game")
    def new_game():
        payload = request.get_json(silent=True) or {}
        human_raw = str(payload.get("human", "x")).lower()
        session_id = str(uuid4())
        state = GameState.initial(config.game)
        display_anchor: Coord | None = config.game.opening_cell() if config.game.bounds() is not None else None
        last_bot_turn: tuple[Coord, ...] = ()
        if human_raw == "watch":
            human_player = None
            bot_search_by_player = {"x": primary_search, "o": opponent_search}
            bot_label_by_player = {"x": primary_label, "o": opponent_label}
        else:
            human_player = "o" if human_raw == "o" else "x"
            bot_player: Player = "o" if human_player == "x" else "x"
            bot_search_by_player = {bot_player: primary_search}
            bot_label_by_player = {bot_player: primary_label}

            if state.to_play == bot_player:
                state, display_anchor, last_bot_turn = _advance_bot_turns(
                    state,
                    bot_search_by_player,
                    config,
                    display_anchor,
                    turn_limit=1,
                )

        sessions[session_id] = SessionState(
            human_player=human_player,
            bot_search_by_player=bot_search_by_player,
            bot_label_by_player=bot_label_by_player,
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
            if not session.state.is_terminal:
                session.state, session.display_anchor, session.last_bot_turn = _advance_bot_turns(
                    session.state,
                    session.bot_search_by_player,
                    config,
                    session.display_anchor,
                    turn_limit=1,
                )
        except IllegalMoveError as exc:
            return jsonify({"error": "illegal_move", "message": str(exc)}), 400

        return jsonify(_session_payload(session_id, session, config))

    @app.post("/api/step/<session_id>")
    def step(session_id: str):
        session = sessions.get(session_id)
        if session is None:
            return jsonify({"error": "unknown_session"}), 404
        if session.state.is_terminal:
            return jsonify(_session_payload(session_id, session, config))
        if session.state.to_play not in session.bot_search_by_player:
            return jsonify({"error": "human_turn", "message": "current player is human-controlled"}), 400

        session.state, session.display_anchor, session.last_bot_turn = _advance_bot_turns(
            session.state,
            session.bot_search_by_player,
            config,
            session.display_anchor,
            turn_limit=1,
        )
        return jsonify(_session_payload(session_id, session, config))

    return app


def _build_bot_search(config: AppConfig, checkpoint_path: str | None):
    if checkpoint_path:
        checkpoint = Path(checkpoint_path)
        if config.search.algorithm == "guided_mcts":
            search = GuidedMctsTurnSearch.from_checkpoint(checkpoint, config)
        else:
            search = ModelGuidedTurnSearch.from_checkpoint(checkpoint, config)
        return search, f"checkpoint: {checkpoint.parent.name}/{checkpoint.name}"
    return BaselineTurnSearch(), "heuristic baseline"


def _apply_human_move(
    session: SessionState,
    cells: tuple[Coord, ...],
    config: AppConfig,
) -> GameState:
    state = session.state
    if state.is_terminal:
        raise IllegalMoveError("game is already over")
    if session.human_player is None:
        raise IllegalMoveError("this session is bot-controlled")
    if state.to_play != session.human_player:
        raise IllegalMoveError("it is not the human player's turn")
    return state.apply_turn(cells, config.game)


def _advance_bot_turns(
    state: GameState,
    bot_search_by_player: dict[Player, object],
    config: AppConfig,
    display_anchor: Coord | None,
    *,
    turn_limit: int,
) -> tuple[GameState, Coord | None, tuple[Coord, ...]]:
    current = state
    anchor = display_anchor
    last_bot_turn: tuple[Coord, ...] = ()
    turns_taken = 0
    while not current.is_terminal and current.to_play in bot_search_by_player and turns_taken < turn_limit:
        search = bot_search_by_player[current.to_play]
        bot_turn = search.choose_turn(current, config)
        current = BaselineTurnSearch.apply_cells(current, bot_turn.cells, config)
        if anchor is None and current.move_history:
            anchor = current.move_history[0].cell
        last_bot_turn = bot_turn.cells
        turns_taken += 1
    return current, anchor, last_bot_turn


def _session_payload(session_id: str, session: SessionState, config: AppConfig) -> dict[str, object]:
    state = session.state
    anchor = session.display_anchor or config.game.opening_cell()
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
    suggested_center = state.suggested_center() if state.stones else config.game.opening_cell()
    board_bounds = config.game.bounds()
    relative_bounds = (
        {
            "min_q": board_bounds[0] - anchor[0],
            "max_q": board_bounds[1] - anchor[0],
            "min_r": board_bounds[2] - anchor[1],
            "max_r": board_bounds[3] - anchor[1],
        }
        if board_bounds is not None
        else None
    )
    return {
        "session_id": session_id,
        "human_player": session.human_player,
        "bot_player": next(iter(session.bot_search_by_player)) if len(session.bot_search_by_player) == 1 else None,
        "mode": "spectator" if session.human_player is None else "human_vs_bot",
        "state": {
            **state.to_mapping(),
            "stones": stones,
            "winning_line": winning_line,
        },
        "last_bot_turn": last_bot_turn,
        "players": {
            "x": session.bot_label_by_player.get("x", "human"),
            "o": session.bot_label_by_player.get("o", "human"),
        },
        "view": {
            "anchor": {"q": anchor[0], "r": anchor[1]},
            "suggested_center": {
                "q": suggested_center[0] - anchor[0],
                "r": suggested_center[1] - anchor[1],
            },
        },
        "config": {
            "board_mode": config.game.board_mode,
            "board_bounds": relative_bounds,
            "win_length": config.game.win_length,
            "opening_placements": config.game.opening_placements,
            "turn_placements": config.game.turn_placements,
        },
    }


def _pluralize(word: str, count: int) -> str:
    return word if count == 1 else f"{word}s"


def _web_bootstrap_payload(
    *,
    config_path: str,
    config: AppConfig,
    bot_label: str,
    board_title: str,
    board_lede: str,
) -> dict[str, object]:
    opening_q, opening_r = config.game.opening_cell()
    board_bounds = config.game.bounds()
    relative_bounds = (
        {
            "min_q": board_bounds[0] - opening_q,
            "max_q": board_bounds[1] - opening_q,
            "min_r": board_bounds[2] - opening_r,
            "max_r": board_bounds[3] - opening_r,
        }
        if board_bounds is not None
        else None
    )
    return {
        "configPath": config_path,
        "configName": Path(config_path).name,
        "botLabel": bot_label,
        "boardTitle": board_title,
        "boardLede": board_lede,
        "game": {
            "boardMode": config.game.board_mode,
            "boardWidth": config.game.board_width,
            "boardHeight": config.game.board_height,
            "winLength": config.game.win_length,
            "openingPlacements": config.game.opening_placements,
            "turnPlacements": config.game.turn_placements,
            "boardBounds": relative_bounds,
            "anchor": {"q": opening_q, "r": opening_r},
        },
    }


def _to_absolute_cells(session: SessionState, relative_cells: tuple[Coord, ...]) -> tuple[Coord, ...]:
    anchor = session.display_anchor or (0, 0)
    return tuple((q + anchor[0], r + anchor[1]) for q, r in relative_cells)
