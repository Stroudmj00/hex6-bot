import json
from pathlib import Path
import pickle
from types import SimpleNamespace

import pytest
import torch

from hex6.config import load_config_with_overrides
from hex6.game import GameState
from hex6.nn import HexPolicyValueNet
from hex6.train.bootstrap import (
    BootstrapExample,
    _merge_replay_buffer_examples,
    _self_play_temperature_for_state,
    generate_bootstrap_examples,
    generate_bootstrap_examples_with_progress,
    train_bootstrap,
)


def test_generate_bootstrap_examples_all_placements_records_second_step() -> None:
    first_only = load_config_with_overrides(
        "configs/play.toml",
            {
                "training": {
                    "bootstrap_strategy": "search_supervision_then_self_play",
                    "bootstrap_games": 1,
                    "max_game_plies": 3,
                    "policy_target": "first_stone_only",
                    "bootstrap_opening_suite": "",
                }
        },
    )
    all_placements = load_config_with_overrides(
        "configs/play.toml",
            {
                "training": {
                    "bootstrap_strategy": "search_supervision_then_self_play",
                    "bootstrap_games": 1,
                    "max_game_plies": 3,
                    "policy_target": "all_placements",
                    "bootstrap_opening_suite": "",
                }
        },
    )

    first_only_examples = generate_bootstrap_examples(first_only, config_path="configs/play.toml")
    all_placement_examples = generate_bootstrap_examples(all_placements, config_path="configs/play.toml")

    assert len(first_only_examples) == 2
    assert len(all_placement_examples) == 3
    assert sum(example.state.placements_remaining == 1 for example in first_only_examples) == 1
    assert sum(example.state.placements_remaining == 1 for example in all_placement_examples) == 2


def test_generate_bootstrap_examples_resolves_opening_suite_relative_to_config(tmp_path: Path) -> None:
    config_path = tmp_path / "nested" / "bootstrap.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        Path("configs/play.toml")
        .read_text(encoding="ascii")
        .replace(
            'bootstrap_opening_suite = "configs/experiments/bootstrap_conversion_opening_suite.toml"',
            'bootstrap_opening_suite = "opening_suite.toml"',
        ),
        encoding="ascii",
    )
    (config_path.parent / "opening_suite.toml").write_text(
        "\n".join(
            [
                "[[scenarios]]",
                'name = "seeded_opening"',
                'description = "start from one stone"',
                "placements = [[0, 0]]",
                'expected_to_play = "o"',
                "expected_placements_remaining = 2",
                "",
            ]
        ),
        encoding="ascii",
    )

    config = load_config_with_overrides(
        config_path,
        {
            "training": {
                "bootstrap_games": 1,
                "max_game_plies": 1,
                "self_play_workers": 1,
            }
        },
    )

    examples = generate_bootstrap_examples(config, config_path=config_path)

    assert examples
    assert examples[0].state.ply_count == 1
    assert examples[0].state.to_play == "o"


def test_generate_bootstrap_examples_rejects_unsupported_policy_target() -> None:
    config = load_config_with_overrides(
        "configs/play.toml",
        {"training": {"policy_target": "bad_target", "bootstrap_opening_suite": ""}},
    )

    with pytest.raises(ValueError, match="unsupported training.policy_target"):
        generate_bootstrap_examples(config, config_path="configs/play.toml")


def test_generate_bootstrap_examples_mixed_start_fraction_uses_seeded_and_empty_games() -> None:
    config = load_config_with_overrides(
        "configs/fast.toml",
        {
            "training": {
                "bootstrap_games": 8,
                "max_game_plies": 1,
                "self_play_workers": 1,
                "bootstrap_seeded_start_fraction": 0.75,
            }
        },
    )
    openings: list[str | None] = []

    generate_bootstrap_examples_with_progress(
        config,
        config_path="configs/fast.toml",
        progress_callback=lambda payload: openings.append(payload["last_opening_name"])
        if payload.get("stage") == "self_play"
        else None,
    )

    assert len(openings) == 8
    assert sum(name is not None for name in openings) == 6
    assert sum(name is None for name in openings) == 2


def test_generate_bootstrap_examples_rejects_invalid_seeded_start_fraction() -> None:
    config = load_config_with_overrides(
        "configs/play.toml",
        {"training": {"bootstrap_seeded_start_fraction": 1.5, "bootstrap_opening_suite": ""}},
    )

    with pytest.raises(ValueError, match="bootstrap_seeded_start_fraction"):
        generate_bootstrap_examples(config, config_path="configs/play.toml")


def test_generate_bootstrap_examples_rejects_invalid_temperature_schedule() -> None:
    config = load_config_with_overrides(
        "configs/fast.toml",
        {"training": {"self_play_temperature_after_drop": -0.1}},
    )

    with pytest.raises(ValueError, match="self_play_temperature_after_drop"):
        generate_bootstrap_examples(config, config_path="configs/fast.toml")


def test_generate_bootstrap_examples_rejects_reanalyse_without_alphazero() -> None:
    config = load_config_with_overrides(
        "configs/play.toml",
        {
            "training": {
                "bootstrap_strategy": "search_supervision_then_self_play",
                "reanalyse_fraction": 0.25,
            }
        },
    )

    with pytest.raises(ValueError, match="reanalyse_fraction requires"):
        generate_bootstrap_examples(config, config_path="configs/play.toml")


def test_generate_bootstrap_examples_rejects_invalid_reanalyse_priority() -> None:
    config = load_config_with_overrides(
        "configs/fast.toml",
        {"training": {"reanalyse_priority": "bad_priority"}},
    )

    with pytest.raises(ValueError, match="reanalyse_priority"):
        generate_bootstrap_examples(config, config_path="configs/fast.toml")


def test_generate_bootstrap_examples_rejects_missing_opening_suite(tmp_path: Path) -> None:
    config_path = tmp_path / "nested" / "bootstrap.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        Path("configs/play.toml")
        .read_text(encoding="ascii")
        .replace(
            'bootstrap_opening_suite = "configs/experiments/bootstrap_conversion_opening_suite.toml"',
            'bootstrap_opening_suite = "missing_suite.toml"',
        ),
        encoding="ascii",
    )
    config = load_config_with_overrides(
        config_path,
        {"training": {"bootstrap_games": 1, "self_play_workers": 1}},
    )

    with pytest.raises(ValueError, match="could not resolve path"):
        generate_bootstrap_examples(config, config_path=config_path)


def test_generate_bootstrap_examples_supports_alphazero_visit_targets() -> None:
    config = load_config_with_overrides(
        "configs/fast.toml",
        {
            "search": {
                "root_simulations": 4,
            },
            "training": {
                "bootstrap_strategy": "alphazero_self_play",
                "bootstrap_games": 1,
                "max_game_plies": 3,
                "policy_target": "visit_distribution",
                "bootstrap_opening_suite": "",
                "bootstrap_seeded_start_fraction": 0.0,
                "self_play_workers": 1,
                "self_play_temperature": 1.0,
            },
        },
    )

    examples = generate_bootstrap_examples(config, config_path="configs/fast.toml")

    assert examples
    assert examples[0].policy_distribution
    assert abs(sum(weight for _, weight in examples[0].policy_distribution) - 1.0) < 1e-6


def test_generate_bootstrap_examples_supports_batched_alphazero_self_play() -> None:
    config = load_config_with_overrides(
        "configs/fast.toml",
        {
            "search": {
                "root_simulations": 4,
                "dirichlet_epsilon": 0.0,
            },
            "training": {
                "bootstrap_strategy": "alphazero_self_play",
                "bootstrap_games": 2,
                "max_game_plies": 3,
                "policy_target": "visit_distribution",
                "bootstrap_opening_suite": "",
                "bootstrap_seeded_start_fraction": 0.0,
                "self_play_workers": 2,
                "self_play_temperature": 1.0,
            },
        },
    )

    examples = generate_bootstrap_examples(config, config_path="configs/fast.toml")

    assert examples
    assert all(example.policy_distribution for example in examples)
    assert all(abs(sum(weight for _, weight in example.policy_distribution) - 1.0) < 1e-6 for example in examples)


def test_self_play_temperature_schedule_switches_after_drop_ply() -> None:
    config = load_config_with_overrides(
        "configs/fast.toml",
        {
            "training": {
                "self_play_temperature": 1.0,
                "self_play_temperature_drop_ply": 2,
                "self_play_temperature_after_drop": 0.0,
            }
        },
    )
    state = GameState.initial(config.game)
    assert _self_play_temperature_for_state(state, config) == 1.0
    state = state.apply_placement((0, 0), config.game)
    assert _self_play_temperature_for_state(state, config) == 1.0
    state = state.apply_placement((1, 0), config.game)
    assert _self_play_temperature_for_state(state, config) == 0.0


def test_train_bootstrap_reuses_replay_buffer_between_runs(tmp_path: Path) -> None:
    config = load_config_with_overrides(
        "configs/play.toml",
        {
            "training": {
                "bootstrap_strategy": "search_supervision_then_self_play",
                "bootstrap_games": 1,
                "max_game_plies": 1,
                "policy_target": "first_stone_only",
                "bootstrap_opening_suite": "",
                "self_play_workers": 1,
                "replay_buffer_size": 10,
            }
        },
    )
    replay_buffer = tmp_path / "replay_buffer.pkl"

    first = train_bootstrap(
        config,
        output_dir=tmp_path / "run1",
        config_path="configs/play.toml",
        replay_buffer_path=replay_buffer,
    )
    second = train_bootstrap(
        config,
        output_dir=tmp_path / "run2",
        config_path="configs/play.toml",
        replay_buffer_path=replay_buffer,
    )

    assert first["replay_buffer_examples"] == first["examples"]
    assert second["replay_buffer_examples"] > second["examples"]


def test_train_bootstrap_records_resource_usage(tmp_path: Path) -> None:
    config = load_config_with_overrides(
        "configs/play.toml",
        {
            "runtime": {
                "resource_poll_seconds": 0.01,
            },
            "training": {
                "bootstrap_strategy": "search_supervision_then_self_play",
                "bootstrap_games": 1,
                "max_game_plies": 1,
                "policy_target": "first_stone_only",
                "bootstrap_opening_suite": "",
                "self_play_workers": 1,
                "replay_buffer_size": 0,
            },
            "evaluation": {
                "arena_games": 0,
            },
        },
    )

    metrics = train_bootstrap(
        config,
        output_dir=tmp_path / "resource_run",
        config_path="configs/play.toml",
    )

    resource_usage_path = Path(str(metrics["resource_usage_path"]))
    assert resource_usage_path.exists()
    payload = json.loads(resource_usage_path.read_text(encoding="ascii"))
    assert payload["summary"]["sample_count"] >= 2
    assert metrics["resource_summary"]["sample_count"] == payload["summary"]["sample_count"]
    assert metrics["record_resource_usage"] is True


def test_merge_replay_buffer_reanalyses_recent_examples(monkeypatch, tmp_path: Path) -> None:
    config = load_config_with_overrides(
        "configs/fast.toml",
        {
            "training": {
                "reanalyse_fraction": 1.0,
                "reanalyse_max_examples": 1,
            }
        },
    )
    previous_state = GameState.initial(config.game).apply_placement((0, 0), config.game)
    current_state = previous_state.apply_placement((1, 0), config.game)
    previous = BootstrapExample(previous_state, (((0, 1), 1.0),), 0.0)
    current = BootstrapExample(current_state, (((1, 1), 1.0),), 0.0)
    replay_buffer_path = tmp_path / "replay.pkl"
    with replay_buffer_path.open("wb") as handle:
        pickle.dump([previous], handle)

    def fake_analyze_roots(self, states, _config, **_kwargs):
        return [
            SimpleNamespace(
                cell_policy=(((2, 2), 1.0),),
                chosen_turn=SimpleNamespace(cells=((2, 2), (2, 3))),
            )
            for _ in states
        ]

    monkeypatch.setattr("hex6.search.guided_mcts.GuidedMctsTurnSearch.analyze_roots", fake_analyze_roots)
    model = HexPolicyValueNet(input_channels=6, channels=config.model.channels, blocks=config.model.blocks)

    merged, metrics = _merge_replay_buffer_examples(
        current_examples=[current],
        config=config,
        model=model,
        device=torch.device("cpu"),
        replay_buffer_path=replay_buffer_path,
        replay_buffer_size=4,
    )

    assert metrics["reanalysed_examples"] == 1
    assert merged[0].policy_distribution == (((2, 2), 1.0),)
    assert merged[1].policy_distribution == current.policy_distribution


def test_merge_replay_buffer_draw_focus_prioritizes_board_exhausted_examples(monkeypatch, tmp_path: Path) -> None:
    config = load_config_with_overrides(
        "configs/fast.toml",
        {
            "training": {
                "reanalyse_fraction": 1.0,
                "reanalyse_max_examples": 1,
                "reanalyse_priority": "draw_focus",
            }
        },
    )
    draw_state = GameState.initial(config.game).apply_placement((0, 0), config.game)
    win_state = draw_state.apply_placement((1, 0), config.game)
    draw_example = BootstrapExample(
        draw_state,
        (((0, 1), 1.0),),
        0.0,
        opening_name="o_must_block_horizontal_press",
        terminal_reason="board_exhausted",
    )
    win_example = BootstrapExample(
        win_state,
        (((1, 1), 1.0),),
        1.0,
        opening_name="x_can_finish_horizontal",
        terminal_reason="win",
    )
    current = BootstrapExample(win_state, (((2, 1), 1.0),), 0.0)
    replay_buffer_path = tmp_path / "replay_draw_focus.pkl"
    with replay_buffer_path.open("wb") as handle:
        pickle.dump([draw_example, win_example], handle)

    def fake_analyze_roots(self, states, _config, **_kwargs):
        return [
            SimpleNamespace(
                cell_policy=(((2, 2), 1.0),),
                chosen_turn=SimpleNamespace(cells=((2, 2), (2, 3))),
            )
            for _ in states
        ]

    monkeypatch.setattr("hex6.search.guided_mcts.GuidedMctsTurnSearch.analyze_roots", fake_analyze_roots)
    model = HexPolicyValueNet(input_channels=6, channels=config.model.channels, blocks=config.model.blocks)

    merged, metrics = _merge_replay_buffer_examples(
        current_examples=[current],
        config=config,
        model=model,
        device=torch.device("cpu"),
        replay_buffer_path=replay_buffer_path,
        replay_buffer_size=8,
    )

    assert metrics["reanalysed_examples"] == 1
    assert merged[0].policy_distribution == (((2, 2), 1.0),)
    assert merged[1].policy_distribution == win_example.policy_distribution
