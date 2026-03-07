from hex6.web import create_app


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
    assert (0, 0) in stones
    assert moved["view"]["anchor"] == {"q": 5, "r": -3}
