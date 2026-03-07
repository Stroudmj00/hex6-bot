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
