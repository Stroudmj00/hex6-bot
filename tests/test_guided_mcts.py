from pathlib import Path

import torch
from torch import nn

from hex6.config import load_config_with_overrides
from hex6.game import GameState
from hex6.nn import HexPolicyValueNet
from hex6.search import GuidedMctsTurnSearch


class CountingModel(nn.Module):
    def __init__(self, inner: nn.Module) -> None:
        super().__init__()
        self.inner = inner
        self.forward_calls = 0
        self.batch_sizes: list[int] = []

    def forward(self, inputs: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        self.forward_calls += 1
        self.batch_sizes.append(int(inputs.shape[0]))
        return self.inner(inputs)


def test_guided_mcts_returns_legal_turn_from_checkpoint(tmp_path: Path) -> None:
    config = load_config_with_overrides(
        "configs/fast.toml",
        {
            "search": {
                "root_simulations": 4,
            }
        },
    )
    model = HexPolicyValueNet(
        input_channels=6,
        channels=config.model.channels,
        blocks=config.model.blocks,
    )
    checkpoint_path = tmp_path / "guided_mcts.pt"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "config_path": "configs/fast.toml",
            "history": [],
        },
        checkpoint_path,
    )

    search = GuidedMctsTurnSearch.from_checkpoint(checkpoint_path, config, device=torch.device("cpu"))
    state = GameState.initial(config.game).apply_placement((0, 0), config.game)

    turn = search.choose_turn(state, config)

    assert len(turn.cells) == state.placements_remaining
    assert len(set(turn.cells)) == len(turn.cells)
    assert all(state.is_empty(cell) for cell in turn.cells)


def test_guided_mcts_from_checkpoint_supports_wider_block_count(tmp_path: Path) -> None:
    source_config = load_config_with_overrides("configs/fast.toml", {"model": {"blocks": 2}})
    target_config = load_config_with_overrides("configs/fast.toml", {"model": {"blocks": 3}})
    model = HexPolicyValueNet(
        input_channels=6,
        channels=source_config.model.channels,
        blocks=source_config.model.blocks,
    )
    checkpoint_path = tmp_path / "guided_mcts_partial.pt"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "config_path": "configs/fast.toml",
            "history": [],
        },
        checkpoint_path,
    )

    search = GuidedMctsTurnSearch.from_checkpoint(checkpoint_path, target_config, device=torch.device("cpu"))
    state = GameState.initial(target_config.game).apply_placement((0, 0), target_config.game)

    turn = search.choose_turn(state, target_config)

    assert len(turn.cells) == state.placements_remaining


def test_guided_mcts_reports_root_policy_distribution() -> None:
    config = load_config_with_overrides(
        "configs/fast.toml",
        {
            "search": {
                "root_simulations": 4,
            }
        },
    )
    model = HexPolicyValueNet(
        input_channels=6,
        channels=config.model.channels,
        blocks=config.model.blocks,
    )
    search = GuidedMctsTurnSearch(model, device=torch.device("cpu"))
    state = GameState.initial(config.game).apply_placement((0, 0), config.game)

    analysis = search.analyze_root(state, config)

    assert analysis.turn_stats
    assert analysis.cell_policy
    assert abs(sum(weight for _, weight in analysis.cell_policy) - 1.0) < 1e-5


def test_guided_mcts_reuses_single_forward_for_policy_and_value_cache() -> None:
    config = load_config_with_overrides(
        "configs/fast.toml",
        {
            "search": {
                "root_simulations": 1,
            }
        },
    )
    model = CountingModel(
        HexPolicyValueNet(
            input_channels=6,
            channels=config.model.channels,
            blocks=config.model.blocks,
        )
    )
    search = GuidedMctsTurnSearch(model, device=torch.device("cpu"))
    state = GameState.initial(config.game).apply_placement((0, 0), config.game)

    policy = search._policy_scores(state, config, state.to_play)  # noqa: SLF001
    value = search._evaluate_value(state, config, state.to_play)  # noqa: SLF001

    assert policy
    assert isinstance(value, float)
    assert model.forward_calls == 1

    search._policy_scores(state, config, state.to_play)  # noqa: SLF001
    search._evaluate_value(state, config, state.to_play)  # noqa: SLF001
    assert model.forward_calls == 1


def test_guided_mcts_analyze_roots_matches_single_root_analysis() -> None:
    config = load_config_with_overrides(
        "configs/fast.toml",
        {
            "search": {
                "root_simulations": 4,
                "dirichlet_epsilon": 0.0,
            }
        },
    )
    model = HexPolicyValueNet(
        input_channels=6,
        channels=config.model.channels,
        blocks=config.model.blocks,
    )
    first_state = GameState.initial(config.game)
    for cell in [(0, 0), (1, 0), (0, 1)]:
        first_state = first_state.apply_placement(cell, config.game)
    second_state = GameState.initial(config.game)
    for cell in [(0, 0), (1, 0), (0, 1), (2, 0), (1, 1)]:
        second_state = second_state.apply_placement(cell, config.game)

    batched = GuidedMctsTurnSearch(model, device=torch.device("cpu"), seed=7)
    batched_analysis = batched.analyze_roots((first_state, second_state), config)

    single_first = GuidedMctsTurnSearch(model, device=torch.device("cpu"), seed=7).analyze_root(first_state, config)
    single_second = GuidedMctsTurnSearch(model, device=torch.device("cpu"), seed=7).analyze_root(second_state, config)

    assert [analysis.chosen_turn.cells for analysis in batched_analysis] == [
        single_first.chosen_turn.cells,
        single_second.chosen_turn.cells,
    ]


def test_guided_mcts_parallel_expansions_preserve_simulation_budget() -> None:
    serial_config = load_config_with_overrides(
        "configs/fast.toml",
        {
            "search": {
                "root_simulations": 5,
                "parallel_expansions_per_root": 1,
                "dirichlet_epsilon": 0.0,
            }
        },
    )
    parallel_config = load_config_with_overrides(
        "configs/fast.toml",
        {
            "search": {
                "root_simulations": 5,
                "parallel_expansions_per_root": 3,
                "dirichlet_epsilon": 0.0,
            }
        },
    )
    model = HexPolicyValueNet(
        input_channels=6,
        channels=serial_config.model.channels,
        blocks=serial_config.model.blocks,
    )
    state = GameState.initial(serial_config.game)
    for cell in [(0, 0), (1, 0), (0, 1), (2, 0), (1, 1)]:
        state = state.apply_placement(cell, serial_config.game)

    serial = GuidedMctsTurnSearch(model, device=torch.device("cpu"), seed=11).analyze_root(state, serial_config)
    parallel = GuidedMctsTurnSearch(model, device=torch.device("cpu"), seed=11).analyze_root(state, parallel_config)

    assert serial.simulations == 5
    assert parallel.simulations == 5
    assert sum(stat.visits for stat in serial.turn_stats) == sum(stat.visits for stat in parallel.turn_stats)
