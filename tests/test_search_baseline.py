from hex6.config import load_config
from hex6.game import GameState
from hex6.search import BaselineTurnSearch


def test_baseline_plays_center_on_empty_opening() -> None:
    config = load_config()
    search = BaselineTurnSearch()
    state = GameState.initial(config.game)

    turn = search.choose_turn(state, config)

    assert turn.cells == ((0, 0),)


def test_baseline_finds_immediate_winning_placement() -> None:
    config = load_config()
    search = BaselineTurnSearch()
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

    turn = search.choose_turn(state, config)

    assert turn.cells == ((5, 0),)
    assert turn.reason == "immediate_win"
