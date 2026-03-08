from hex6.config import load_config


def test_load_default_config() -> None:
    config = load_config()
    assert config.game.win_length == 6
    assert config.prototype.allow_long_range_islands is True
    assert config.search.algorithm == "guided_mcts"
    assert config.runtime.cpu_threads == 12
    assert config.runtime.enable_tf32 is True
    assert config.integration.status_backend == "none"
    assert config.integration.github_branch == "colab-status"
    assert config.evaluation.arena_games == 8
    assert config.evaluation.record_game_history is True
    assert config.training.self_play_workers == 4
    assert config.training.pin_memory is True
