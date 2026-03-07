import pytest

from hex6.config import load_config
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

    state = state.apply_placement((10, 0), config.game)
    assert state.to_play == "o"
    assert state.placements_remaining == 1
    assert state.turn_index == 2

    state = state.apply_placement((11, 0), config.game)
    assert state.to_play == "x"
    assert state.placements_remaining == 2
    assert state.turn_index == 3


def test_far_away_move_is_still_legal_on_sparse_infinite_board() -> None:
    config = load_config()
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


def test_winning_placement_ends_the_game_immediately() -> None:
    config = load_config()
    state = GameState.initial(config.game)

    scripted_moves = (
        (0, 0),
        (10, 0),
        (11, 0),
        (1, 0),
        (2, 0),
        (10, 1),
        (11, 1),
        (3, 0),
        (4, 0),
        (10, 2),
        (11, 2),
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
