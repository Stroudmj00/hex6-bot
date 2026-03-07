from pathlib import Path

from hex6.config import apply_overrides, load_config_mapping, load_config_with_overrides
from hex6.eval.search_matrix import load_search_matrix, resolved_base_config_path


def test_apply_overrides_merges_nested_sections() -> None:
    base = load_config_mapping("configs/play.toml")
    merged = apply_overrides(
        base,
        {
            "prototype": {"first_stone_candidate_limit": 7},
            "search": {"shallow_reply_width": 2},
        },
    )

    assert merged["prototype"]["first_stone_candidate_limit"] == 7
    assert merged["search"]["shallow_reply_width"] == 2
    assert merged["game"]["win_length"] == 6


def test_load_config_with_overrides_returns_typed_config() -> None:
    config = load_config_with_overrides(
        "configs/play.toml",
        {
            "prototype": {"second_stone_candidate_limit": 2},
            "heuristic": {"include_candidate_edge": True},
        },
    )

    assert config.prototype.second_stone_candidate_limit == 2
    assert config.heuristic.include_candidate_edge is True


def test_load_search_matrix_uses_matrix_relative_base_path() -> None:
    matrix_path = Path("configs/experiments/search_matrix.toml")
    base_config, games, variants = load_search_matrix(matrix_path)

    assert resolved_base_config_path(matrix_path, "../play.toml").name == "play.toml"
    assert base_config.search.algorithm == "baseline_play"
    assert games == 4
    assert len(variants) == 6
