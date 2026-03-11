from pathlib import Path

from hex6.config import load_config
from hex6.eval.openings import load_opening_suite


def test_load_opening_suite_builds_non_terminal_states() -> None:
    config = load_config("configs/play.toml")
    suite = load_opening_suite(Path("configs/experiments/opening_suite.toml"), config)

    assert len(suite) == 6
    assert suite[0].state.to_play == "o"
    assert suite[0].state.placements_remaining == 2
    assert suite[0].state.is_terminal is False
    assert suite[1].state.to_play == "x"
    assert suite[1].state.placements_remaining == 2
    assert suite[1].state.is_terminal is False


def test_opening_suite_positions_respect_default_board_bounds() -> None:
    config = load_config("configs/fast.toml")
    suite = load_opening_suite(Path("configs/experiments/opening_suite.toml"), config)

    assert suite
    for opening in suite:
        assert all(config.game.is_in_bounds(cell) for cell in opening.state.stones)


def test_promotion_opening_suite_expands_translation_coverage() -> None:
    config = load_config("configs/fast.toml")
    suite = load_opening_suite(Path("configs/experiments/promotion_opening_suite.toml"), config)

    assert len(suite) == 12
    assert suite[6].name == "o_must_block_horizontal_shifted"
    assert suite[11].name == "x_can_finish_diagonal_shifted"
    for opening in suite:
        assert all(config.game.is_in_bounds(cell) for cell in opening.state.stones)


def test_conversion_bootstrap_suite_targets_defend_then_convert_positions() -> None:
    config = load_config("configs/fast.toml")
    suite = load_opening_suite(Path("configs/experiments/bootstrap_conversion_opening_suite.toml"), config)

    assert [opening.name for opening in suite] == [
        "o_must_block_horizontal_press",
        "o_must_block_vertical_press",
        "o_must_block_diagonal_press",
    ]
    for opening in suite:
        assert opening.state.to_play == "o"
        assert opening.state.placements_remaining == 2
        assert opening.state.is_terminal is False
        assert all(config.game.is_in_bounds(cell) for cell in opening.state.stones)


def test_conversion_eval_suites_cover_press_and_finish_cases() -> None:
    config = load_config("configs/fast.toml")
    standard = load_opening_suite(Path("configs/experiments/conversion_opening_suite.toml"), config)
    promotion = load_opening_suite(Path("configs/experiments/promotion_conversion_opening_suite.toml"), config)

    assert len(standard) == 6
    assert standard[0].name == "o_must_block_horizontal_press"
    assert standard[-1].name == "x_can_finish_diagonal"
    assert len(promotion) == 12
    assert promotion[6].name == "o_must_block_horizontal_press_shifted"
    assert promotion[11].name == "x_can_finish_diagonal_shifted"
    for opening in standard + promotion:
        assert all(config.game.is_in_bounds(cell) for cell in opening.state.stones)
