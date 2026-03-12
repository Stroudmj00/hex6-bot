from pathlib import Path

import pytest

from hex6.config import load_config
from hex6.game import GameState
from hex6.web import create_app
from hex6.web.app import SessionState, _apply_human_move


class FakeClock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_index_highlights_local_modes_and_rules() -> None:
    app = create_app("configs/play.toml")
    client = app.test_client()

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Play vs Champion" in html
    assert "Play vs Browser AI" in html
    assert "Play vs Friend" in html
    assert "Watch Engine Match" in html
    assert "Animated rule cards instead of static text" in html
    assert "window.HEX6_BOOTSTRAP" in html


def test_index_reflects_configured_turn_counts(tmp_path: Path) -> None:
    custom_config = tmp_path / "play_custom.toml"
    custom_config.write_text(
        Path("configs/play.toml").read_text(encoding="utf-8")
        .replace("opening_placements = 1", "opening_placements = 2")
        .replace("turn_placements = 2", "turn_placements = 3"),
        encoding="utf-8",
    )

    app = create_app(str(custom_config))
    client = app.test_client()

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Opening turn places 2 stones, then each turn places 3 stones." in html
    assert "2 opening / 3 after" in html


def test_new_game_endpoint_returns_session_state() -> None:
    app = create_app("configs/play.toml")
    client = app.test_client()

    response = client.post("/api/new-game", json={"human": "x"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["human_player"] == "x"
    assert payload["state"]["to_play"] == "x"
    assert payload["state"]["placements_remaining"] == 1
    assert "session_id" in payload


def test_first_human_move_becomes_display_origin() -> None:
    app = create_app("configs/play.toml")
    client = app.test_client()

    response = client.post("/api/new-game", json={"human": "x"})
    payload = response.get_json()

    move_response = client.post(
        f"/api/play/{payload['session_id']}",
        json={"cells": [{"q": 5, "r": -3}]},
    )
    moved = move_response.get_json()

    assert move_response.status_code == 200
    stones = {(stone["q"], stone["r"]) for stone in moved["state"]["stones"]}
    assert (5, -3) in stones
    assert moved["view"]["anchor"] == {"q": 0, "r": 0}


def test_human_move_allows_short_winning_prefix() -> None:
    config = load_config()
    state = GameState.initial(config.game)
    scripted_moves = (
        (0, 0),
        (-7, 0),
        (-6, 0),
        (1, 0),
        (2, 0),
        (-7, 1),
        (-6, 1),
        (3, 0),
        (4, 0),
        (-7, 2),
        (-6, 2),
    )
    for move in scripted_moves:
        state = state.apply_placement(move, config.game)

    session = SessionState(
        human_player="x",
        bot_search_by_player={"o": object()},
        bot_label_by_player={"o": "bot"},
        state=state,
    )

    winning_state = _apply_human_move(session, ((5, 0),), config)

    assert winning_state.is_terminal is True
    assert winning_state.winner == "x"


def test_spectator_session_can_step_bots() -> None:
    app = create_app("configs/play.toml")
    client = app.test_client()

    response = client.post("/api/new-game", json={"human": "watch"})
    assert response.status_code == 200
    payload = response.get_json()

    assert payload["mode"] == "spectator"
    assert payload["human_player"] is None

    step_response = client.post(f"/api/step/{payload['session_id']}")
    stepped = step_response.get_json()

    assert step_response.status_code == 200
    assert stepped["state"]["ply_count"] >= 1
    assert len(stepped["last_bot_turn"]) >= 1


def test_bounded_web_payload_exposes_board_bounds() -> None:
    app = create_app("configs/play.toml")
    client = app.test_client()

    response = client.post("/api/new-game", json={"human": "x"})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["config"]["board_bounds"] == {
        "min_q": -7,
        "max_q": 7,
        "min_r": -7,
        "max_r": 7,
    }


def test_create_invite_returns_invite_code() -> None:
    app = create_app("configs/play.toml")
    client = app.test_client()

    response = client.post("/api/create-invite", json={"human": "x"})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["mode"] == "human_vs_human"
    assert payload["assigned_player"] == "x"
    assert isinstance(payload.get("invite_code"), str)
    assert len(payload["invite_code"]) == 6
    assert payload["session_id"]


def test_two_players_can_join_and_take_turns() -> None:
    app = create_app("configs/play.toml")
    client = app.test_client()

    host = client.post("/api/create-invite", json={"human": "x"}).get_json()
    code = host["invite_code"]
    join = client.post(f"/api/join-invite/{code}").get_json()
    assert join["assigned_player"] == "o"
    assert join["session_id"] == host["session_id"]

    play_x = client.post(
        f"/api/play/{host['session_id']}",
        json={"cells": [{"q": 0, "r": 0}], "player": "x"},
    )
    assert play_x.status_code == 200

    play_o = client.post(
        f"/api/play/{host['session_id']}",
        json={"cells": [{"q": 1, "r": 0}], "player": "o"},
    )
    played_o = play_o.get_json()
    assert play_o.status_code == 200
    assert played_o["state"]["ply_count"] == 2

    bad = client.post(f"/api/play/{host['session_id']}", json={"cells": [{"q": 2, "r": 0}]})
    bad_payload = bad.get_json()
    assert bad.status_code == 400
    assert bad_payload["error"] == "invalid_request"


def test_healthz_reports_web_runtime_metadata() -> None:
    app = create_app("configs/play.toml")
    client = app.test_client()

    response = client.get("/healthz")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["board_mode"] == "sparse_bounded"


@pytest.mark.parametrize(
    ("body", "message_fragment"),
    [
        ({"cells": "bad"}, "cells must be a JSON array"),
        ({"cells": [{"q": "0", "r": 0}]}, "cells[0].q must be an integer"),
        ({"cells": [{"q": 0}]}, "cells[0] must include both q and r"),
    ],
)
def test_play_rejects_malformed_payloads(body: dict[str, object], message_fragment: str) -> None:
    app = create_app("configs/play.toml")
    client = app.test_client()

    response = client.post("/api/new-game", json={"human": "x"})
    payload = response.get_json()

    bad_response = client.post(f"/api/play/{payload['session_id']}", json=body)
    bad_payload = bad_response.get_json()

    assert bad_response.status_code == 400
    assert bad_payload["error"] == "invalid_request"
    assert message_fragment in bad_payload["message"]


def test_new_game_rejects_non_object_json_payload() -> None:
    app = create_app("configs/play.toml")
    client = app.test_client()

    response = client.post("/api/new-game", json=["watch"])
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["error"] == "invalid_request"


def test_session_store_evicts_oldest_session_when_capacity_is_exceeded() -> None:
    app = create_app("configs/play.toml", max_sessions=1)
    client = app.test_client()

    first = client.post("/api/new-game", json={"human": "x"}).get_json()
    second = client.post("/api/new-game", json={"human": "x"}).get_json()

    assert client.get(f"/api/state/{first['session_id']}").status_code == 404
    assert client.get(f"/api/state/{second['session_id']}").status_code == 200


def test_session_store_expires_idle_sessions() -> None:
    clock = FakeClock()
    app = create_app("configs/play.toml", session_ttl_seconds=5.0, clock=clock)
    client = app.test_client()

    payload = client.post("/api/new-game", json={"human": "x"}).get_json()
    clock.advance(6.0)
    response = client.get(f"/api/state/{payload['session_id']}")

    assert response.status_code == 404
