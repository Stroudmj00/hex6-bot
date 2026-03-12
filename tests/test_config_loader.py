from hex6.config import load_config


def test_load_default_config() -> None:
    config = load_config()
    assert config.game.board_mode == "sparse_bounded"
    assert config.game.board_width == 15
    assert config.game.board_height == 15
    assert config.game.win_length == 6
    assert config.prototype.allow_long_range_islands is True
    assert config.search.algorithm == "guided_mcts"
    assert config.runtime.cpu_threads == 12
    assert config.runtime.enable_tf32 is True
    assert config.runtime.record_resource_usage is True
    assert config.runtime.resource_poll_seconds == 5.0
    assert config.integration.status_backend == "none"
    assert config.integration.github_branch == "colab-status"
    assert config.evaluation.arena_games == 8
    assert config.evaluation.max_game_plies == 0
    assert config.evaluation.board_width_override == 0
    assert config.evaluation.board_height_override == 0
    assert config.evaluation.post_train_eval == "tournament"
    assert config.evaluation.post_train_max_game_plies == 0
    assert config.evaluation.promotion_games_per_match == 12
    assert config.evaluation.promotion_opening_suite == "configs/experiments/promotion_conversion_opening_suite.toml"
    assert config.evaluation.promotion_include_baseline is True
    assert config.evaluation.promotion_require_candidate_rank_one is True
    assert config.evaluation.promotion_min_score_delta == 0.5
    assert config.evaluation.record_game_history is True
    assert config.training.self_play_workers == 4
    assert config.training.max_game_plies == 0
    assert config.training.pin_memory is True
    assert config.training.bootstrap_strategy == "alphazero_self_play"
    assert config.training.policy_target == "visit_distribution"
    assert config.training.bootstrap_opening_suite == "configs/experiments/bootstrap_conversion_opening_suite.toml"
    assert config.training.bootstrap_seeded_start_fraction == 0.75
    assert config.training.self_play_temperature == 1.0
    assert config.training.self_play_temperature_drop_ply == 24
    assert config.training.self_play_temperature_after_drop == 0.2
    assert config.training.reanalyse_fraction == 0.0
    assert config.training.reanalyse_max_examples == 0
    assert config.training.reanalyse_priority == "recent"
    assert config.runtime.record_resource_usage is True
    assert config.runtime.resource_poll_seconds == 5.0
    assert config.search.reply_depth == 1
    assert config.search.puct_exploration == 1.25
    assert config.search.dirichlet_alpha == 0.35
    assert config.search.dirichlet_epsilon == 0.25
    assert config.search.root_policy_mode == "visit_count"
    assert config.search.root_gumbel_scale == 1.0


def test_load_fast_config() -> None:
    config = load_config("configs/fast.toml")

    assert config.game.board_mode == "sparse_bounded"
    assert config.game.board_width == 15
    assert config.game.board_height == 15
    assert config.search.reply_depth == 1
    assert config.search.puct_exploration == 1.25
    assert config.prototype.first_stone_candidate_limit == 6
    assert config.prototype.second_stone_candidate_limit == 2
    assert config.search.shallow_reply_width == 1
    assert config.training.bootstrap_opening_suite == "configs/experiments/bootstrap_conversion_opening_suite.toml"
    assert config.training.bootstrap_strategy == "alphazero_self_play"
    assert config.training.policy_target == "visit_distribution"
    assert config.training.self_play_workers == 4
    assert config.training.self_play_temperature_drop_ply == 24
    assert config.training.self_play_temperature_after_drop == 0.2
    assert config.training.reanalyse_fraction == 0.0
    assert config.training.reanalyse_max_examples == 0
    assert config.training.reanalyse_priority == "recent"
    assert config.evaluation.promotion_games_per_match == 12
    assert config.search.root_simulations == 48
    assert config.search.parallel_expansions_per_root == 1
    assert config.search.root_policy_mode == "visit_count"
    assert config.search.root_gumbel_scale == 1.0
    assert config.evaluation.board_width_override == 0
    assert config.evaluation.board_height_override == 0
    assert config.evaluation.post_train_opening_suite == "configs/experiments/conversion_opening_suite.toml"
    assert config.evaluation.promotion_opening_suite == "configs/experiments/promotion_conversion_opening_suite.toml"


def test_load_play_config() -> None:
    config = load_config("configs/play.toml")

    assert config.game.board_mode == "sparse_bounded"
    assert config.game.board_width == 15
    assert config.game.board_height == 15
    assert config.search.reply_depth == 1
    assert config.training.bootstrap_strategy == "alphazero_self_play"
    assert config.training.bootstrap_opening_suite == "configs/experiments/bootstrap_conversion_opening_suite.toml"
    assert config.game.opening_cell() == (0, 0)
    assert config.game.bounds() == (-7, 7, -7, 7)
    assert config.evaluation.board_width_override == 0
    assert config.evaluation.board_height_override == 0
    assert config.evaluation.promotion_include_baseline is True
    assert config.runtime.record_resource_usage is True


def test_load_board_ablation_configs() -> None:
    config_19 = load_config("configs/fast_19.toml")
    config_25 = load_config("configs/fast_25.toml")

    assert config_19.game.board_width == 19
    assert config_19.game.board_height == 19
    assert config_19.game.bounds() == (-9, 9, -9, 9)
    assert config_19.evaluation.board_width_override == 0
    assert config_19.evaluation.board_height_override == 0
    assert config_25.game.board_width == 25
    assert config_25.game.board_height == 25
    assert config_25.game.bounds() == (-12, 12, -12, 12)
    assert config_25.evaluation.board_width_override == 0
    assert config_25.evaluation.board_height_override == 0
    assert config_19.evaluation.promotion_opening_suite == "configs/experiments/promotion_opening_suite.toml"
    assert config_25.evaluation.promotion_opening_suite == "configs/experiments/promotion_opening_suite.toml"


def test_load_local_16h_best_config() -> None:
    config = load_config("configs/local_16h_best.toml")

    assert config.search.root_simulations == 64
    assert config.search.parallel_expansions_per_root == 1
    assert config.prototype.first_stone_candidate_limit == 8
    assert config.prototype.second_stone_candidate_limit == 3
    assert config.search.shallow_reply_width == 2
    assert config.training.bootstrap_games == 8
    assert config.training.epochs == 2
    assert config.training.replay_buffer_size == 30000
    assert config.training.symmetry_augmentation is True
    assert config.training.self_play_workers == 4
    assert config.model.architecture == "hex_resnet_tiny"
    assert config.model.channels == 16
    assert config.evaluation.board_width_override == 0
    assert config.evaluation.board_height_override == 0
    assert config.integration.status_backend == "none"
    assert config.runtime.resource_poll_seconds == 5.0


def test_load_local_4h_strongest_config() -> None:
    config = load_config("configs/local_4h_strongest.toml")

    assert config.search.root_simulations == 64
    assert config.search.parallel_expansions_per_root == 4
    assert config.training.self_play_workers == 8
    assert config.training.bootstrap_games == 8
    assert config.training.batch_size == 24
    assert config.training.replay_buffer_size == 40000
    assert config.model.board_crop_radius == 8
    assert config.model.channels == 16
    assert config.model.blocks == 2
    assert config.evaluation.board_width_override == 0
    assert config.evaluation.board_height_override == 0
    assert config.training.reanalyse_fraction == 0.0
    assert config.training.reanalyse_max_examples == 0
    assert config.training.reanalyse_priority == "recent"
    assert config.runtime.record_resource_usage is True


def test_load_local_4h_strongest_v2_config() -> None:
    config = load_config("configs/local_4h_strongest_v2.toml")

    assert config.search.root_simulations == 96
    assert config.search.parallel_expansions_per_root == 6
    assert config.training.bootstrap_opening_suite == "configs/experiments/bootstrap_conversion_opening_suite_v2.toml"
    assert config.evaluation.board_width_override == 0
    assert config.evaluation.board_height_override == 0
    assert config.training.reanalyse_fraction == 0.125
    assert config.training.reanalyse_max_examples == 64
    assert config.training.reanalyse_priority == "draw_focus"
    assert config.model.blocks == 3
    assert config.runtime.record_resource_usage is True
    assert config.search.root_policy_mode == "visit_count"
    assert config.search.root_gumbel_scale == 1.0


def test_load_colab_strongest_v2_config() -> None:
    config = load_config("configs/colab_strongest_v2.toml")

    assert config.search.root_simulations == 96
    assert config.search.parallel_expansions_per_root == 6
    assert config.training.bootstrap_opening_suite == "configs/experiments/bootstrap_conversion_opening_suite_v2.toml"
    assert config.training.reanalyse_fraction == 0.125
    assert config.training.reanalyse_max_examples == 64
    assert config.training.reanalyse_priority == "draw_focus"
    assert config.model.blocks == 3
    assert config.integration.status_backend == "github_branch"
    assert config.search.root_policy_mode == "visit_count"
    assert config.search.root_gumbel_scale == 1.0


def test_load_local_4h_strongest_v2_gumbel_config() -> None:
    config = load_config("configs/local_4h_strongest_v2_gumbel.toml")

    assert config.search.root_simulations == 96
    assert config.search.parallel_expansions_per_root == 6
    assert config.search.root_policy_mode == "gumbel"
    assert config.search.root_gumbel_scale == 1.0
    assert config.training.bootstrap_opening_suite == "configs/experiments/bootstrap_conversion_opening_suite_v2.toml"
    assert config.training.reanalyse_priority == "draw_focus"
