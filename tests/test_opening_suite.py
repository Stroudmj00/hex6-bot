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
