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
