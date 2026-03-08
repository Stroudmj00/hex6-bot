from hex6.config import load_config
from hex6.prototype import SparsePosition


def test_live_and_dead_cells_are_disjoint() -> None:
    config = load_config()
    position = SparsePosition(
        stones={
            (0, 0): "x",
            (1, 0): "x",
            (0, 1): "o",
            (1, 1): "o",
        },
        to_play="x",
    )

    live = position.live_cells(config)
    dead = position.globally_dead_cells(config)
    assert not (live["x"] & dead)
    assert not (live["o"] & dead)


def test_candidate_scores_return_ranked_cells() -> None:
    config = load_config()
    position = SparsePosition(
        stones={
            (0, 0): "x",
            (1, 0): "x",
            (2, 0): "x",
            (0, 1): "o",
            (1, 1): "o",
        },
        to_play="x",
    )

    scored = position.top_first_stone_candidates(config)
    assert scored
    assert scored[0].total >= scored[-1].total


def test_candidate_scores_preserve_tactical_feature_counts() -> None:
    config = load_config("configs/play.toml")
    position = SparsePosition(
        stones={
            (0, 0): "x",
            (1, 0): "x",
            (2, 0): "x",
            (0, 1): "o",
            (1, 1): "o",
        },
        to_play="x",
    )

    best = position.candidate_scores(config)[0]

    assert best.cell == (-1, 0)
    assert best.frontier_contacts == 1
    assert best.friendly_open_windows == 18
    assert best.enemy_open_windows == 13
    assert best.best_friendly_alignment == 3
    assert best.best_enemy_alignment == 0
    assert best.friendly_pressure == 31.0
    assert best.enemy_pressure == 0.0
    assert best.intersection_count == 31
    assert best.island_bonus == 0.0
    assert best.space_bonus == 1.0
    assert best.total == 129.7
