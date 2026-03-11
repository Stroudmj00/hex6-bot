import pytest

from hex6.config import load_config, load_config_with_overrides
from hex6.game import GameState, IllegalMoveError


def test_initial_state_uses_configured_opening_turn() -> None:
    config = load_config()
    state = GameState.initial(config.game)

    assert state.to_play == "x"
    assert state.placements_remaining == config.game.opening_placements
    assert state.turn_index == 1
    assert state.ply_count == 0
    assert state.is_terminal is False


def test_opening_move_hands_turn_to_second_player() -> None:
    config = load_config()
    state = GameState.initial(config.game)

    state = state.apply_placement((0, 0), config.game)

    assert state.stones[(0, 0)] == "x"
    assert state.to_play == "o"
    assert state.placements_remaining == config.game.turn_placements
    assert state.turn_index == 2
    assert state.ply_count == 1


def test_two_stone_turn_stays_with_same_player_until_completed() -> None:
    config = load_config()
    state = GameState.initial(config.game).apply_placement((0, 0), config.game)

    state = state.apply_placement((5, 0), config.game)
    assert state.to_play == "o"
    assert state.placements_remaining == 1
    assert state.turn_index == 2

    state = state.apply_placement((6, 0), config.game)
    assert state.to_play == "x"
    assert state.placements_remaining == 2
    assert state.turn_index == 3


def test_far_away_move_is_still_legal_on_sparse_infinite_board() -> None:
    config = load_config_with_overrides(
        "configs/default.toml",
        {
            "game": {
                "board_mode": "sparse_infinite",
                "board_width": 0,
                "board_height": 0,
            }
        },
    )
    state = GameState.initial(config.game).apply_placement((0, 0), config.game)

    state = state.apply_placement((10_000, -10_000), config.game)

    assert state.stones[(10_000, -10_000)] == "o"
    assert state.to_play == "o"
    assert state.placements_remaining == 1


def test_occupied_cell_is_illegal() -> None:
    config = load_config()
    state = GameState.initial(config.game).apply_placement((0, 0), config.game)

    with pytest.raises(IllegalMoveError):
        state.apply_placement((0, 0), config.game)


def test_bounded_board_rejects_out_of_bounds_move() -> None:
    config = load_config("configs/fast.toml")
    state = GameState.initial(config.game).apply_placement((0, 0), config.game)

    assert state.is_legal_placement((7, 7), config.game) is True
    assert state.is_legal_placement((8, 0), config.game) is False

    with pytest.raises(IllegalMoveError):
        state.apply_placement((8, 0), config.game)


def test_bounded_board_enters_terminal_draw_when_next_turn_cannot_be_completed() -> None:
    config = load_config_with_overrides(
        "configs/fast.toml",
        {
            "game": {
                "board_width": 1,
                "board_height": 3,
            }
        },
    )
    state = GameState.initial(config.game)

    state = state.apply_placement((0, 0), config.game)
    state = state.apply_placement((0, -1), config.game)
    state = state.apply_placement((0, 1), config.game)

    assert state.is_terminal is True
    assert state.winner is None
    assert state.draw_reason == "board_exhausted"
    assert state.placements_remaining == 0


def test_winning_placement_ends_the_game_immediately() -> None:
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

    assert state.to_play == "x"
    assert state.placements_remaining == 2

    winning_state = state.apply_placement((5, 0), config.game)
    assert winning_state.is_terminal is True
    assert winning_state.winner == "x"
    assert winning_state.placements_remaining == 0
    assert winning_state.winning_line == ((0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0))

    with pytest.raises(IllegalMoveError):
        state.apply_turn(((5, 0), (6, 0)), config.game)


def test_apply_turn_accepts_short_winning_prefix() -> None:
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

    winning_state = state.apply_turn(((5, 0),), config.game)

    assert winning_state.is_terminal is True
    assert winning_state.winner == "x"
    assert winning_state.placements_remaining == 0


def test_apply_placement_can_skip_history_but_keeps_last_move() -> None:
    config = load_config("configs/fast.toml")
    state = GameState.initial(config.game)

    state = state.apply_placement((0, 0), config.game, record_history=False)
    state = state.apply_placement((1, 0), config.game, record_history=False)

    assert state.move_history == ()
    assert state.last_move == (1, 0)
    assert state.ply_count == 2
