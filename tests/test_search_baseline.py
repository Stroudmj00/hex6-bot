from hex6.config import load_config, load_config_with_overrides
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

    assert turn.reason == "immediate_win"


def test_baseline_threat_search_prefers_spread_out_two_stone_win() -> None:
    config = load_config_with_overrides(
        "configs/default.toml",
        {
            "search": {"tactical_solver": "threat_search"},
            "prototype": {"first_stone_candidate_limit": 0, "second_stone_candidate_limit": 0},
        },
    )
    search = BaselineTurnSearch()
    state = GameState(
        stones={
            (0, 0): "x",
            (2, 0): "x",
            (3, 0): "x",
            (5, 0): "x",
        },
        to_play="x",
        placements_remaining=2,
        turn_index=9,
        ply_count=8,
    )

    turn = search.choose_turn(state, config)

    assert turn.cells == ((1, 0), (4, 0))
    assert turn.reason == "immediate_win"


def test_baseline_threat_search_forces_opponent_immediate_defense() -> None:
    config = load_config_with_overrides(
        "configs/default.toml",
        {
            "search": {"tactical_solver": "threat_search"},
            "prototype": {"first_stone_candidate_limit": 0, "second_stone_candidate_limit": 0},
        },
    )
    search = BaselineTurnSearch()
    state = GameState(
        stones={
            (0, 0): "o",
            (1, 0): "o",
            (2, 0): "o",
            (3, 0): "o",
            (4, 0): "o",
        },
        to_play="x",
        placements_remaining=2,
        turn_index=7,
        ply_count=12,
    )

    turn = search.choose_turn(state, config)

    assert turn.cells == ((-1, 0), (5, 0))
    assert turn.reason == "forced_defense"


def test_baseline_threat_search_finds_low_width_immediate_win() -> None:
    config = load_config_with_overrides(
        "configs/default.toml",
        {
            "search": {"tactical_solver": "threat_search", "shallow_reply_width": 1},
            "prototype": {"first_stone_candidate_limit": 1, "second_stone_candidate_limit": 1},
        },
    )
    search = BaselineTurnSearch()
    state = GameState(
        stones={
            (-2, -2): "x",
            (-2, 3): "o",
            (-1, -3): "o",
            (-1, 0): "o",
            (-1, 1): "o",
            (-1, 2): "o",
            (-1, 3): "x",
            (0, -3): "x",
            (0, -2): "x",
            (0, -1): "x",
            (0, 0): "x",
            (1, -1): "x",
            (2, -1): "o",
        },
        to_play="o",
        placements_remaining=2,
        turn_index=8,
        ply_count=13,
    )

    turn = search.choose_turn(state, config)

    assert turn.cells == ((-1, -2), (-1, -1))
    assert turn.reason == "immediate_win"


def test_baseline_threat_search_finds_low_width_forced_block() -> None:
    config = load_config_with_overrides(
        "configs/default.toml",
        {
            "search": {"tactical_solver": "threat_search", "shallow_reply_width": 1},
            "prototype": {"first_stone_candidate_limit": 1, "second_stone_candidate_limit": 1},
        },
    )
    search = BaselineTurnSearch()
    state = GameState(
        stones={
            (-4, 2): "o",
            (-4, 3): "x",
            (-4, 4): "x",
            (-3, 2): "o",
            (-3, 3): "x",
            (-3, 4): "o",
            (-2, 2): "o",
            (-2, 3): "x",
            (-1, 1): "o",
            (-1, 3): "o",
            (0, -1): "x",
            (0, 0): "x",
            (0, 1): "o",
            (0, 2): "o",
            (1, 0): "x",
            (1, 1): "x",
        },
        to_play="x",
        placements_remaining=1,
        turn_index=9,
        ply_count=16,
    )

    turn = search.choose_turn(state, config)

    assert turn.cells == ((-1, 2),)
    assert turn.reason == "forced_defense"


def test_baseline_threat_search_returns_full_legal_turn_for_wider_turn_sizes() -> None:
    config = load_config_with_overrides(
        "configs/default.toml",
        {
            "game": {"turn_placements": 3},
            "search": {"tactical_solver": "threat_search"},
            "prototype": {"first_stone_candidate_limit": 1, "second_stone_candidate_limit": 1},
        },
    )
    search = BaselineTurnSearch()
    state = GameState(
        stones={
            (0, 0): "o",
            (1, 0): "o",
            (2, 0): "o",
            (3, 0): "o",
            (4, 0): "o",
        },
        to_play="x",
        placements_remaining=3,
        turn_index=7,
        ply_count=12,
    )

    turn = search.choose_turn(state, config)

    assert len(turn.cells) == 3
    assert {(-1, 0), (5, 0)}.issubset(set(turn.cells))
    assert turn.reason == "forced_defense"


def test_baseline_single_placement_turn_uses_reply_aware_scoring() -> None:
    config = load_config("configs/fast.toml")
    search = BaselineTurnSearch()
    state = GameState(
        stones={
            (0, 0): "x",
            (1, 0): "x",
            (2, 0): "x",
            (3, 0): "x",
            (4, 0): "x",
            (10, 0): "o",
            (11, 0): "o",
        },
        to_play="o",
        placements_remaining=1,
        turn_index=5,
        ply_count=7,
    )

    turn = search.choose_turn(state, config)

    assert state.placements_remaining == 1
    assert turn.cells == ((5, 0),)
    assert turn.reason == "single_step_heuristic"
    assert turn.reply_score == turn.score


def test_baseline_heuristic_mode_uses_heuristic_search_path() -> None:
    config = load_config("configs/fast.toml")
    search = BaselineTurnSearch()
    state = GameState(
        stones={
            (0, 0): "x",
            (2, 0): "x",
            (4, 0): "x",
            (6, 0): "x",
            (10, 0): "o",
            (11, 0): "o",
        },
        to_play="o",
        placements_remaining=2,
        turn_index=6,
        ply_count=8,
    )

    turn = search.choose_turn(state, config)

    assert turn.reason in {"reply_aware", "single_step_heuristic"}
