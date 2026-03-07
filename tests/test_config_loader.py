from hex6.config import load_config


def test_load_default_config() -> None:
    config = load_config()
    assert config.game.win_length == 6
    assert config.prototype.allow_long_range_islands is True
    assert config.search.algorithm == "guided_mcts"

