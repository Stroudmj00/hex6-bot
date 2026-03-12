"""Bootstrap training loop using search-generated self-play."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
import json
import math
import multiprocessing as mp
import os
from pathlib import Path
import pickle
import time
from typing import Callable, Iterable

import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from hex6.config import AppConfig, load_config
from hex6.eval.openings import OpeningScenario, load_opening_suite
from hex6.game import Coord, GameState
from hex6.game.symmetry import rotate_coord, rotate_state
from hex6.nn import HexPolicyValueNet, cell_to_policy_index, encode_state, load_compatible_state_dict
from hex6.search import BaselineTurnSearch, GuidedMctsTurnSearch, ScoredTurn
from hex6.train.resource_usage import ResourceMonitor


SUPPORTED_POLICY_TARGETS = frozenset({"first_stone_only", "all_placements", "visit_distribution"})
SUPPORTED_BOOTSTRAP_STRATEGIES = frozenset({"search_supervision_then_self_play", "alphazero_self_play"})
SUPPORTED_REANALYSE_PRIORITIES = frozenset({"recent", "draw_focus"})


@dataclass(frozen=True)
class BootstrapExample:
    state: GameState
    policy_distribution: tuple[tuple[Coord, float], ...]
    value_target: float
    opening_name: str | None = None
    terminal_reason: str | None = None


@dataclass(frozen=True)
class BootstrapGameResult:
    game_index: int
    winner: str | None
    plies: int
    opening_name: str | None
    termination: str | None
    examples: tuple[BootstrapExample, ...]


@dataclass
class _ActiveAlphaZeroGame:
    game_index: int
    state: GameState
    opening_name: str | None
    starting_ply: int
    ply_limit: int | None
    trajectory: list[tuple[GameState, tuple[tuple[Coord, float], ...]]]


class BootstrapDataset(Dataset[tuple[torch.Tensor, torch.Tensor, torch.Tensor]]):
    def __init__(self, examples: list[BootstrapExample], config: AppConfig) -> None:
        inputs: list[torch.Tensor] = []
        policy_targets: list[torch.Tensor] = []
        value_targets: list[float] = []

        for example in examples:
            encoded = encode_state(example.state, config)
            target = torch.zeros(len(encoded.index_to_cell), dtype=torch.float32)
            total_mass = 0.0
            for cell, weight in example.policy_distribution:
                policy_index = cell_to_policy_index(encoded, cell)
                if policy_index is None or weight <= 0.0:
                    continue
                target[policy_index] += float(weight)
                total_mass += float(weight)
            if total_mass <= 0.0:
                continue
            inputs.append(encoded.tensor)
            policy_targets.append(target / total_mass)
            value_targets.append(example.value_target)

        if not inputs:
            raise ValueError("bootstrap dataset is empty after encoding")

        self.inputs = torch.stack(inputs)
        self.policy_targets = torch.stack(policy_targets)
        self.value_targets = torch.tensor(value_targets, dtype=torch.float32)

    def __len__(self) -> int:
        return len(self.policy_targets)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        return (
            self.inputs[index],
            self.policy_targets[index],
            self.value_targets[index],
        )


ProgressCallback = Callable[[dict[str, object]], None]


def generate_bootstrap_examples(
    config: AppConfig,
    *,
    config_path: str | Path = "configs/default.toml",
) -> list[BootstrapExample]:
    return generate_bootstrap_examples_with_progress(config, config_path=config_path)


def generate_bootstrap_examples_with_progress(
    config: AppConfig,
    *,
    config_path: str | Path = "configs/default.toml",
    progress_path: Path | None = None,
    progress_callback: ProgressCallback | None = None,
    model: HexPolicyValueNet | None = None,
    device: torch.device | None = None,
) -> list[BootstrapExample]:
    _validate_policy_target(config.training.policy_target)
    _validate_bootstrap_strategy(config.training.bootstrap_strategy)
    _validate_bootstrap_seeded_start_fraction(config.training.bootstrap_seeded_start_fraction)
    _validate_self_play_temperature_schedule(
        temperature=config.training.self_play_temperature,
        drop_ply=config.training.self_play_temperature_drop_ply,
        after_drop=config.training.self_play_temperature_after_drop,
    )
    _validate_reanalyse_settings(config)
    examples: list[BootstrapExample] = []
    total_games = config.training.bootstrap_games
    workers = max(1, min(config.training.self_play_workers, total_games))
    opening_suite = _load_bootstrap_opening_suite(config, config_path)

    if config.training.bootstrap_strategy == "alphazero_self_play":
        search_device = device or _select_device(config)
        search_model = model or HexPolicyValueNet(
            input_channels=6,
            channels=config.model.channels,
            blocks=config.model.blocks,
        ).to(search_device)
        search = GuidedMctsTurnSearch(search_model, device=search_device)
        if workers == 1:
            for game_index in range(total_games):
                result = _generate_alphazero_bootstrap_game(
                    game_index,
                    config,
                    search=search,
                    total_games=total_games,
                    opening_suite=opening_suite,
                )
                _collect_game_result(
                    result,
                    examples,
                    total_games=total_games,
                    completed_games=game_index + 1,
                    progress_path=progress_path,
                    progress_callback=progress_callback,
                )
        else:
            completed_games = 0
            for result in _generate_alphazero_bootstrap_games_batched(
                config,
                search=search,
                total_games=total_games,
                opening_suite=opening_suite,
                batch_size=workers,
            ):
                completed_games += 1
                _collect_game_result(
                    result,
                    examples,
                    total_games=total_games,
                    completed_games=completed_games,
                    progress_path=progress_path,
                    progress_callback=progress_callback,
                )
        return examples

    if workers == 1 or total_games <= 1:
        for game_index in range(total_games):
            result = _generate_bootstrap_game(
                game_index,
                config,
                total_games=total_games,
                opening_suite=opening_suite,
            )
            _collect_game_result(
                result,
                examples,
                total_games=total_games,
                completed_games=game_index + 1,
                progress_path=progress_path,
                progress_callback=progress_callback,
            )
        return examples

    context = _self_play_mp_context()
    with ProcessPoolExecutor(max_workers=workers, mp_context=context) as executor:
        futures = [
            executor.submit(
                _generate_bootstrap_game,
                game_index,
                config,
                total_games=total_games,
                opening_suite=opening_suite,
            )
            for game_index in range(total_games)
        ]
        completed_games = 0
        for future in as_completed(futures):
            result = future.result()
            completed_games += 1
            _collect_game_result(
                result,
                examples,
                total_games=total_games,
                completed_games=completed_games,
                progress_path=progress_path,
                progress_callback=progress_callback,
            )

    return examples


def train_bootstrap(
    config: AppConfig | None = None,
    output_dir: str | Path = "artifacts/bootstrap",
    config_path: str = "configs/default.toml",
    progress_callback: ProgressCallback | None = None,
    final_stage: str = "complete",
    init_checkpoint_path: str | Path | None = None,
    replay_buffer_path: str | Path | None = None,
) -> dict[str, float | int | str]:
    config = config or load_config()
    configure_runtime(config)
    overall_started = time.perf_counter()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    progress_path = output_path / "progress.json"
    resource_usage_path = output_path / "resource_usage.json"
    _emit_progress(progress_path, progress_callback, {"stage": "starting"})
    device = _select_device(config)
    model, init_report = _build_model(config, device, init_checkpoint_path=init_checkpoint_path)
    resource_monitor = ResourceMonitor(
        enabled=config.runtime.record_resource_usage,
        poll_seconds=config.runtime.resource_poll_seconds,
        device=device,
    )
    resource_monitor.start()

    try:
        self_play_started = time.perf_counter()
        examples = generate_bootstrap_examples_with_progress(
            config,
            config_path=config_path,
            progress_path=progress_path,
            progress_callback=progress_callback,
            model=model,
            device=device,
        )
        self_play_seconds = round(time.perf_counter() - self_play_started, 3)
        replay_started = time.perf_counter()
        replay_examples, reanalyse_metrics = _merge_replay_buffer_examples(
            current_examples=examples,
            config=config,
            model=model,
            device=device,
            replay_buffer_path=Path(replay_buffer_path) if replay_buffer_path is not None else None,
            replay_buffer_size=config.training.replay_buffer_size,
        )
        replay_seconds = round(time.perf_counter() - replay_started, 3)

        dataset_started = time.perf_counter()
        dataset = BootstrapDataset(replay_examples, config)
        pin_memory = config.training.pin_memory and device.type == "cuda"
        loader_kwargs = {
            "batch_size": config.training.batch_size,
            "shuffle": True,
            "num_workers": config.training.data_loader_workers,
            "pin_memory": pin_memory,
        }
        if config.training.data_loader_workers > 0:
            loader_kwargs["persistent_workers"] = True
        loader = DataLoader(dataset, **loader_kwargs)
        dataset_seconds = round(time.perf_counter() - dataset_started, 3)
        _emit_progress(
            progress_path,
            progress_callback,
            {
                "stage": "dataset_ready",
                "examples": len(examples),
                "replay_buffer_examples": len(replay_examples),
                "reanalyse_examples": reanalyse_metrics["reanalysed_examples"],
                "encoded_examples": len(dataset),
                "self_play_seconds": self_play_seconds,
                "replay_seconds": replay_seconds,
                "dataset_seconds": dataset_seconds,
            },
        )

        optimizer = torch.optim.AdamW(model.parameters(), lr=config.training.learning_rate)
        value_loss_fn = nn.MSELoss()
        use_amp = device.type == "cuda" and config.training.mixed_precision
        scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

        history: list[dict[str, float]] = []
        model.train()
        train_started = time.perf_counter()
        for epoch in range(config.training.epochs):
            policy_total = 0.0
            value_total = 0.0
            batch_count = 0

            for batch_inputs, batch_policy, batch_value in loader:
                batch_inputs = batch_inputs.to(device, non_blocking=pin_memory)
                batch_policy = batch_policy.to(device, non_blocking=pin_memory)
                batch_value = batch_value.to(device, non_blocking=pin_memory)

                optimizer.zero_grad(set_to_none=True)
                with torch.amp.autocast(device_type=device.type, enabled=use_amp):
                    policy_logits, value = model(batch_inputs)
                    policy_loss = _soft_cross_entropy(policy_logits, batch_policy)
                    value_loss = value_loss_fn(value, batch_value)
                    loss = policy_loss + value_loss

                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()

                policy_total += float(policy_loss.detach().cpu())
                value_total += float(value_loss.detach().cpu())
                batch_count += 1

            history.append(
                {
                    "epoch": epoch + 1,
                    "policy_loss": policy_total / max(batch_count, 1),
                    "value_loss": value_total / max(batch_count, 1),
                }
            )
            print(
                f"[train] epoch {epoch + 1}/{config.training.epochs} "
                f"policy_loss={history[-1]['policy_loss']:.4f} "
                f"value_loss={history[-1]['value_loss']:.4f}"
            )
            _emit_progress(
                progress_path,
                progress_callback,
                {
                    "stage": "training",
                    "epoch": epoch + 1,
                    "epochs": config.training.epochs,
                    "history": history,
                },
            )

        training_seconds = round(time.perf_counter() - train_started, 3)
        checkpoint_path = output_path / "bootstrap_model.pt"
        torch.save(
            {
                "model_state_dict": model.state_dict(),
                "config_path": config_path,
                "history": history,
            },
            checkpoint_path,
        )

        total_seconds = round(time.perf_counter() - overall_started, 3)
        resource_payload = resource_monitor.stop(output_path=resource_usage_path)
        metrics = {
            "device": str(device),
            "examples": len(examples),
            "replay_buffer_examples": len(replay_examples),
            "encoded_examples": len(dataset),
            "epochs": config.training.epochs,
            "final_policy_loss": history[-1]["policy_loss"],
            "final_value_loss": history[-1]["value_loss"],
            "checkpoint": str(checkpoint_path),
            "self_play_seconds": self_play_seconds,
            "replay_seconds": replay_seconds,
            "dataset_seconds": dataset_seconds,
            "training_seconds": training_seconds,
            "total_seconds": total_seconds,
            "self_play_examples_per_second": round(len(examples) / max(self_play_seconds, 1e-9), 3),
            "training_examples_per_second": round((len(dataset) * config.training.epochs) / max(training_seconds, 1e-9), 3),
            "self_play_workers": config.training.self_play_workers,
            "data_loader_workers": config.training.data_loader_workers,
            "cpu_threads": torch.get_num_threads(),
            "interop_threads": torch.get_num_interop_threads(),
            "bootstrap_strategy": config.training.bootstrap_strategy,
            "policy_target": config.training.policy_target,
            "bootstrap_opening_suite": config.training.bootstrap_opening_suite,
            "bootstrap_seeded_start_fraction": config.training.bootstrap_seeded_start_fraction,
            "bootstrap_target_seeded_games": _target_seeded_game_count(
                config.training.bootstrap_games,
                config.training.bootstrap_seeded_start_fraction,
            ),
            "self_play_temperature": config.training.self_play_temperature,
            "self_play_temperature_drop_ply": config.training.self_play_temperature_drop_ply,
            "self_play_temperature_after_drop": config.training.self_play_temperature_after_drop,
            "reanalyse_fraction": config.training.reanalyse_fraction,
            "reanalyse_max_examples": config.training.reanalyse_max_examples,
            "reanalysed_examples": reanalyse_metrics["reanalysed_examples"],
            "record_resource_usage": config.runtime.record_resource_usage,
            "resource_poll_seconds": config.runtime.resource_poll_seconds,
            "resource_usage_path": str(resource_usage_path),
            "resource_summary": resource_payload.get("summary", {}),
        }
        if init_checkpoint_path is not None:
            metrics["init_checkpoint"] = str(init_checkpoint_path)
            metrics.update(init_report)
        if replay_buffer_path is not None:
            metrics["replay_buffer_path"] = str(replay_buffer_path)

        with (output_path / "metrics.json").open("w", encoding="ascii") as handle:
            json.dump(metrics, handle, indent=2)
        _emit_progress(progress_path, progress_callback, {"stage": final_stage, **metrics})

        return metrics
    except Exception:
        resource_monitor.stop(output_path=resource_usage_path)
        raise


def configure_runtime(config: AppConfig) -> None:
    if config.runtime.cpu_threads > 0:
        torch.set_num_threads(config.runtime.cpu_threads)
    if config.runtime.interop_threads > 0:
        try:
            if torch.get_num_interop_threads() != config.runtime.interop_threads:
                torch.set_num_interop_threads(config.runtime.interop_threads)
        except RuntimeError:
            pass

    if torch.cuda.is_available():
        if hasattr(torch, "set_float32_matmul_precision") and config.runtime.enable_tf32:
            torch.set_float32_matmul_precision("high")
        if hasattr(torch.backends, "cuda") and hasattr(torch.backends.cuda, "matmul"):
            torch.backends.cuda.matmul.allow_tf32 = config.runtime.enable_tf32
        if hasattr(torch.backends, "cudnn"):
            torch.backends.cudnn.allow_tf32 = config.runtime.enable_tf32
            torch.backends.cudnn.benchmark = config.runtime.cudnn_benchmark


def _build_model(
    config: AppConfig,
    device: torch.device,
    *,
    init_checkpoint_path: str | Path | None = None,
) -> tuple[HexPolicyValueNet, dict[str, int]]:
    model = HexPolicyValueNet(
        input_channels=6,
        channels=config.model.channels,
        blocks=config.model.blocks,
    ).to(device)
    if init_checkpoint_path is None:
        return model, {}

    checkpoint = torch.load(init_checkpoint_path, map_location=device)
    load_report = load_compatible_state_dict(model, checkpoint["model_state_dict"])
    return model, load_report


def _soft_cross_entropy(logits: torch.Tensor, target_distribution: torch.Tensor) -> torch.Tensor:
    log_probs = torch.log_softmax(logits, dim=1)
    return -(target_distribution * log_probs).sum(dim=1).mean()


def _select_device(config: AppConfig) -> torch.device:
    if config.runtime.preferred_device == "cuda" and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    with path.open("w", encoding="ascii") as handle:
        json.dump(payload, handle, indent=2)


def _emit_progress(
    progress_path: Path | None,
    progress_callback: ProgressCallback | None,
    payload: dict[str, object],
) -> None:
    if progress_path is not None:
        _write_json(progress_path, payload)
    if progress_callback is not None:
        progress_callback(payload)


def _collect_game_result(
    result: BootstrapGameResult,
    examples: list[BootstrapExample],
    *,
    total_games: int,
    completed_games: int,
    progress_path: Path | None,
    progress_callback: ProgressCallback | None,
) -> None:
    print(
        f"[self-play] game {result.game_index + 1}/{total_games} "
        f"completed: plies={result.plies} "
        f"opening={result.opening_name or 'empty_board'} "
        f"winner={result.winner or 'draw'}"
    )
    examples.extend(result.examples)
    if progress_path is not None or progress_callback is not None:
        _emit_progress(
            progress_path,
            progress_callback,
            {
                "stage": "self_play",
                "completed_games": completed_games,
                "total_games": total_games,
                "examples_so_far": len(examples),
                "last_winner": result.winner,
                "last_game_plies": result.plies,
                "last_game_index": result.game_index + 1,
                "last_opening_name": result.opening_name,
            },
        )


def _generate_bootstrap_game(
    game_index: int,
    config: AppConfig,
    *,
    total_games: int,
    opening_suite: tuple[OpeningScenario, ...] = (),
) -> BootstrapGameResult:
    search = BaselineTurnSearch()
    opening = _select_bootstrap_opening(
        game_index=game_index,
        total_games=total_games,
        opening_suite=opening_suite,
        seeded_start_fraction=config.training.bootstrap_seeded_start_fraction,
    )
    state = opening.state if opening else GameState.initial(config.game)
    ply_limit = _effective_relative_ply_cap(
        configured_limit=config.training.max_game_plies,
        config=config,
        starting_ply=state.ply_count,
    )
    trajectory: list[tuple[GameState, tuple[tuple[Coord, float], ...]]] = []

    while not state.is_terminal and (ply_limit is None or state.ply_count < ply_limit):
        turn = search.choose_turn(state, config)
        state = _record_turn_examples(
            state=state,
            cells=turn.cells,
            config=config,
            trajectory=trajectory,
        )

    winner = state.winner
    termination = state.draw_reason or ("win" if winner is not None else None)
    examples: list[BootstrapExample] = []
    for position, policy_distribution in trajectory:
        value_target = 0.0 if winner is None else (1.0 if position.to_play == winner else -1.0)
        examples.append(
            BootstrapExample(
                position,
                policy_distribution,
                value_target,
                opening_name=opening.name if opening else None,
                terminal_reason=termination,
            )
        )

        if config.training.symmetry_augmentation:
            for steps in range(1, 6):
                examples.append(
                    BootstrapExample(
                        state=rotate_state(position, steps),
                        policy_distribution=_rotate_policy_distribution(policy_distribution, steps),
                        value_target=value_target,
                        opening_name=opening.name if opening else None,
                        terminal_reason=termination,
                    )
                )

    return BootstrapGameResult(
        game_index=game_index,
        winner=winner,
        plies=max(0, state.ply_count - (opening.state.ply_count if opening else 0)),
        opening_name=opening.name if opening else None,
        termination=termination,
        examples=tuple(examples),
    )


def _generate_alphazero_bootstrap_game(
    game_index: int,
    config: AppConfig,
    *,
    search: GuidedMctsTurnSearch,
    total_games: int,
    opening_suite: tuple[OpeningScenario, ...] = (),
) -> BootstrapGameResult:
    opening = _select_bootstrap_opening(
        game_index=game_index,
        total_games=total_games,
        opening_suite=opening_suite,
        seeded_start_fraction=config.training.bootstrap_seeded_start_fraction,
    )
    state = opening.state if opening else GameState.initial(config.game)
    ply_limit = _effective_relative_ply_cap(
        configured_limit=config.training.max_game_plies,
        config=config,
        starting_ply=state.ply_count,
    )
    trajectory: list[tuple[GameState, tuple[tuple[Coord, float], ...]]] = []

    while not state.is_terminal and (ply_limit is None or state.ply_count < ply_limit):
        analysis = search.analyze_root(
            state,
            config,
            sample=False,
            temperature=None,
            add_root_noise=True,
        )
        analysis = _retarget_root_analysis_temperature(analysis, state=state, config=config)
        trajectory.append((state, _policy_distribution_for_analysis(analysis, config)))
        state = state.apply_turn(analysis.chosen_turn.cells, config.game, record_history=False)

    return _finalize_bootstrap_game_result(
        game_index=game_index,
        final_state=state,
        starting_ply=opening.state.ply_count if opening else 0,
        opening_name=opening.name if opening else None,
        trajectory=trajectory,
        config=config,
    )


def _generate_alphazero_bootstrap_games_batched(
    config: AppConfig,
    *,
    search: GuidedMctsTurnSearch,
    total_games: int,
    opening_suite: tuple[OpeningScenario, ...] = (),
    batch_size: int,
) -> Iterable[BootstrapGameResult]:
    next_game_index = 0
    active_games: list[_ActiveAlphaZeroGame] = []

    while len(active_games) < batch_size and next_game_index < total_games:
        active_games.append(
            _start_alphazero_game(
                game_index=next_game_index,
                config=config,
                total_games=total_games,
                opening_suite=opening_suite,
            )
        )
        next_game_index += 1

    while active_games:
        analyses = search.analyze_roots(
            [game.state for game in active_games],
            config,
            sample=False,
            temperature=None,
            add_root_noise=True,
        )

        still_active: list[_ActiveAlphaZeroGame] = []
        for game, analysis in zip(active_games, analyses, strict=True):
            analysis = _retarget_root_analysis_temperature(
                analysis,
                state=game.state,
                config=config,
            )
            game.trajectory.append((game.state, _policy_distribution_for_analysis(analysis, config)))
            game.state = game.state.apply_turn(analysis.chosen_turn.cells, config.game, record_history=False)
            if game.state.is_terminal or (game.ply_limit is not None and game.state.ply_count >= game.ply_limit):
                yield _finalize_bootstrap_game_result(
                    game_index=game.game_index,
                    final_state=game.state,
                    starting_ply=game.starting_ply,
                    opening_name=game.opening_name,
                    trajectory=game.trajectory,
                    config=config,
                )
                continue
            still_active.append(game)

        active_games = still_active
        while len(active_games) < batch_size and next_game_index < total_games:
            active_games.append(
                _start_alphazero_game(
                    game_index=next_game_index,
                    config=config,
                    total_games=total_games,
                    opening_suite=opening_suite,
                )
            )
            next_game_index += 1


def _start_alphazero_game(
    *,
    game_index: int,
    config: AppConfig,
    total_games: int,
    opening_suite: tuple[OpeningScenario, ...],
) -> _ActiveAlphaZeroGame:
    opening = _select_bootstrap_opening(
        game_index=game_index,
        total_games=total_games,
        opening_suite=opening_suite,
        seeded_start_fraction=config.training.bootstrap_seeded_start_fraction,
    )
    state = opening.state if opening else GameState.initial(config.game)
    return _ActiveAlphaZeroGame(
        game_index=game_index,
        state=state,
        opening_name=opening.name if opening else None,
        starting_ply=state.ply_count,
        ply_limit=_effective_relative_ply_cap(
            configured_limit=config.training.max_game_plies,
            config=config,
            starting_ply=state.ply_count,
        ),
        trajectory=[],
    )


def _finalize_bootstrap_game_result(
    *,
    game_index: int,
    final_state: GameState,
    starting_ply: int,
    opening_name: str | None,
    trajectory: list[tuple[GameState, tuple[tuple[Coord, float], ...]]],
    config: AppConfig,
) -> BootstrapGameResult:
    winner = final_state.winner
    termination = final_state.draw_reason or ("win" if winner is not None else None)
    examples: list[BootstrapExample] = []
    for position, policy_distribution in trajectory:
        value_target = 0.0 if winner is None else (1.0 if position.to_play == winner else -1.0)
        examples.append(
            BootstrapExample(
                position,
                policy_distribution,
                value_target,
                opening_name=opening_name,
                terminal_reason=termination,
            )
        )

        if config.training.symmetry_augmentation:
            for steps in range(1, 6):
                examples.append(
                    BootstrapExample(
                        state=rotate_state(position, steps),
                        policy_distribution=_rotate_policy_distribution(policy_distribution, steps),
                        value_target=value_target,
                        opening_name=opening_name,
                        terminal_reason=termination,
                    )
                )

    return BootstrapGameResult(
        game_index=game_index,
        winner=winner,
        plies=max(0, final_state.ply_count - starting_ply),
        opening_name=opening_name,
        termination=termination,
        examples=tuple(examples),
    )


def _self_play_mp_context() -> mp.context.BaseContext:
    if os.name == "nt":
        return mp.get_context("spawn")
    return mp.get_context("fork")


def _record_turn_examples(
    *,
    state: GameState,
    cells: tuple[Coord, ...],
    config: AppConfig,
    trajectory: list[tuple[GameState, tuple[tuple[Coord, float], ...]]],
) -> GameState:
    policy_target = config.training.policy_target
    if policy_target == "visit_distribution":
        trajectory.append((state, _cell_distribution(cells)))
        return state.apply_turn(cells, config.game, record_history=False)

    current_state = state
    for placement_index, cell in enumerate(cells):
        if policy_target == "all_placements" or placement_index == 0:
            trajectory.append((current_state, ((cell, 1.0),)))
        current_state = current_state.apply_placement(cell, config.game, record_history=False)
        if current_state.is_terminal:
            break
    return current_state


def _policy_distribution_for_analysis(
    analysis,
    config: AppConfig,
) -> tuple[tuple[Coord, float], ...]:
    if config.training.policy_target == "visit_distribution" and analysis.cell_policy:
        return analysis.cell_policy
    return _cell_distribution(analysis.chosen_turn.cells)


def _self_play_temperature_for_state(state: GameState, config: AppConfig) -> float:
    drop_ply = config.training.self_play_temperature_drop_ply
    if drop_ply > 0 and state.ply_count >= drop_ply:
        return config.training.self_play_temperature_after_drop
    return config.training.self_play_temperature


def _retarget_root_analysis_temperature(
    analysis,
    *,
    state: GameState,
    config: AppConfig,
):
    temperature = _self_play_temperature_for_state(state, config)
    if not analysis.turn_stats:
        return analysis

    weights = _weights_from_turn_stats(analysis.turn_stats, temperature)
    chosen_index = _sample_index(weights)
    chosen_stat = analysis.turn_stats[chosen_index]
    return type(analysis)(
        chosen_turn=ScoredTurn(
            cells=chosen_stat.cells,
            score=round(chosen_stat.mean_value, 4),
            reply_score=round(chosen_stat.mean_value, 4),
            evaluation_score=round(chosen_stat.prior, 4),
            reason="guided_mcts",
        ),
        turn_stats=analysis.turn_stats,
        cell_policy=_cell_policy_from_turn_stats(analysis.turn_stats, weights),
        simulations=analysis.simulations,
    )


def _weights_from_turn_stats(
    turn_stats: tuple,
    temperature: float,
) -> list[float]:
    if not turn_stats:
        return []
    if temperature <= 1e-6:
        best_index = max(
            range(len(turn_stats)),
            key=lambda index: (turn_stats[index].visits, turn_stats[index].mean_value, turn_stats[index].prior),
        )
        return [1.0 if index == best_index else 0.0 for index in range(len(turn_stats))]
    weights = [max(stat.visits, 1) ** (1.0 / temperature) for stat in turn_stats]
    total = sum(weights)
    return [weight / total for weight in weights]


def _sample_index(weights: list[float]) -> int:
    threshold = torch.rand(1).item()
    cumulative = 0.0
    for index, weight in enumerate(weights):
        cumulative += weight
        if threshold <= cumulative:
            return index
    return max(0, len(weights) - 1)


def _cell_policy_from_turn_stats(turn_stats: tuple, weights: list[float]) -> tuple[tuple[Coord, float], ...]:
    mass: dict[Coord, float] = {}
    for stat, weight in zip(turn_stats, weights, strict=True):
        share = weight / max(len(stat.cells), 1)
        for cell in stat.cells:
            mass[cell] = mass.get(cell, 0.0) + share
    total = sum(mass.values())
    if total <= 0.0:
        return ()
    return tuple(
        (cell, round(value / total, 6))
        for cell, value in sorted(mass.items(), key=lambda item: (-item[1], item[0]))
    )


def _cell_distribution(cells: tuple[Coord, ...]) -> tuple[tuple[Coord, float], ...]:
    if not cells:
        return ()
    weight = 1.0 / len(cells)
    return tuple((cell, weight) for cell in cells)


def _rotate_policy_distribution(
    policy_distribution: tuple[tuple[Coord, float], ...],
    steps: int,
) -> tuple[tuple[Coord, float], ...]:
    return tuple((rotate_coord(cell, steps), weight) for cell, weight in policy_distribution)


def _validate_policy_target(policy_target: str) -> None:
    if policy_target not in SUPPORTED_POLICY_TARGETS:
        raise ValueError(f"unsupported training.policy_target: {policy_target}")


def _validate_bootstrap_strategy(bootstrap_strategy: str) -> None:
    if bootstrap_strategy not in SUPPORTED_BOOTSTRAP_STRATEGIES:
        raise ValueError(f"unsupported training.bootstrap_strategy: {bootstrap_strategy}")


def _validate_bootstrap_seeded_start_fraction(seeded_start_fraction: float) -> None:
    if seeded_start_fraction < 0.0 or seeded_start_fraction > 1.0:
        raise ValueError(
            "training.bootstrap_seeded_start_fraction must be between 0.0 and 1.0; "
            f"received {seeded_start_fraction}"
        )


def _validate_self_play_temperature_schedule(
    *,
    temperature: float,
    drop_ply: int,
    after_drop: float,
) -> None:
    if temperature < 0.0:
        raise ValueError(f"training.self_play_temperature must be >= 0.0; received {temperature}")
    if drop_ply < 0:
        raise ValueError(f"training.self_play_temperature_drop_ply must be >= 0; received {drop_ply}")
    if after_drop < 0.0:
        raise ValueError(
            "training.self_play_temperature_after_drop must be >= 0.0; "
            f"received {after_drop}"
        )


def _validate_reanalyse_settings(config: AppConfig) -> None:
    fraction = config.training.reanalyse_fraction
    if fraction < 0.0 or fraction > 1.0:
        raise ValueError(f"training.reanalyse_fraction must be between 0.0 and 1.0; received {fraction}")
    if config.training.reanalyse_max_examples < 0:
        raise ValueError(
            "training.reanalyse_max_examples must be >= 0; "
            f"received {config.training.reanalyse_max_examples}"
        )
    if config.training.reanalyse_priority not in SUPPORTED_REANALYSE_PRIORITIES:
        raise ValueError(
            "training.reanalyse_priority must be one of "
            f"{sorted(SUPPORTED_REANALYSE_PRIORITIES)}; received {config.training.reanalyse_priority}"
        )
    if fraction > 0.0 and config.training.bootstrap_strategy != "alphazero_self_play":
        raise ValueError("training.reanalyse_fraction requires training.bootstrap_strategy = 'alphazero_self_play'")


def _merge_replay_buffer_examples(
    *,
    current_examples: list[BootstrapExample],
    config: AppConfig,
    model: HexPolicyValueNet,
    device: torch.device,
    replay_buffer_path: Path | None,
    replay_buffer_size: int,
) -> tuple[list[BootstrapExample], dict[str, int]]:
    if replay_buffer_path is None or replay_buffer_size <= 0:
        return current_examples, {"reanalysed_examples": 0}

    previous_examples = _load_replay_buffer(replay_buffer_path)
    merged = (previous_examples + current_examples)[-replay_buffer_size:]
    reanalysed_examples = 0
    carryover_examples = max(0, len(merged) - len(current_examples))
    if carryover_examples > 0 and config.training.reanalyse_fraction > 0.0:
        merged, reanalysed_examples = _reanalyse_recent_examples(
            merged_examples=merged,
            carryover_examples=carryover_examples,
            config=config,
            model=model,
            device=device,
        )
    replay_buffer_path.parent.mkdir(parents=True, exist_ok=True)
    with replay_buffer_path.open("wb") as handle:
        pickle.dump(merged, handle)
    return merged, {"reanalysed_examples": reanalysed_examples}


def _load_replay_buffer(path: Path) -> list[BootstrapExample]:
    if not path.exists():
        return []
    with path.open("rb") as handle:
        loaded = pickle.load(handle)
    return list(loaded)


def _reanalyse_recent_examples(
    *,
    merged_examples: list[BootstrapExample],
    carryover_examples: int,
    config: AppConfig,
    model: HexPolicyValueNet,
    device: torch.device,
) -> tuple[list[BootstrapExample], int]:
    target = int(round(carryover_examples * config.training.reanalyse_fraction))
    if config.training.reanalyse_max_examples > 0:
        target = min(target, config.training.reanalyse_max_examples)
    target = min(target, carryover_examples)
    if target <= 0:
        return merged_examples, 0

    search = GuidedMctsTurnSearch(model, device=device)
    batch_size = max(1, config.training.self_play_workers)
    refreshed = list(merged_examples)
    selected_indices = _select_reanalysis_indices(
        merged_examples=refreshed,
        carryover_examples=carryover_examples,
        target=target,
        priority=config.training.reanalyse_priority,
    )
    for batch_start in range(0, len(selected_indices), batch_size):
        batch_indices = selected_indices[batch_start : batch_start + batch_size]
        batch_examples = [refreshed[index] for index in batch_indices]
        analyses = search.analyze_roots(
            [example.state for example in batch_examples],
            config,
            sample=False,
            temperature=None,
            add_root_noise=False,
        )
        for example_index, example, analysis in zip(batch_indices, batch_examples, analyses, strict=True):
            refreshed[example_index] = BootstrapExample(
                state=example.state,
                policy_distribution=_policy_distribution_for_analysis(analysis, config),
                value_target=example.value_target,
                opening_name=example.opening_name,
                terminal_reason=example.terminal_reason,
            )
    return refreshed, target


def _select_reanalysis_indices(
    *,
    merged_examples: list[BootstrapExample],
    carryover_examples: int,
    target: int,
    priority: str,
) -> list[int]:
    if target <= 0 or carryover_examples <= 0:
        return []
    if priority == "recent":
        start_index = max(0, carryover_examples - target)
        return list(range(start_index, carryover_examples))

    ranked = sorted(
        range(carryover_examples),
        key=lambda index: (
            merged_examples[index].terminal_reason == "board_exhausted",
            (merged_examples[index].opening_name or "").startswith("o_must_block_"),
            index,
        ),
        reverse=True,
    )
    return sorted(ranked[:target])


def _load_bootstrap_opening_suite(
    config: AppConfig,
    config_path: str | Path,
) -> tuple[OpeningScenario, ...]:
    suite_path = config.training.bootstrap_opening_suite.strip()
    if not suite_path or config.training.bootstrap_seeded_start_fraction <= 0.0:
        return ()
    return tuple(load_opening_suite(_resolve_path_relative_to_config(config_path, suite_path), config))


def _select_bootstrap_opening(
    *,
    game_index: int,
    total_games: int,
    opening_suite: tuple[OpeningScenario, ...],
    seeded_start_fraction: float,
) -> OpeningScenario | None:
    if not opening_suite or total_games <= 0:
        return None

    seeded_games = _target_seeded_game_count(total_games, seeded_start_fraction)
    if seeded_games <= 0:
        return None

    previous_seeded = (game_index * seeded_games) // total_games
    current_seeded = ((game_index + 1) * seeded_games) // total_games
    if current_seeded == previous_seeded:
        return None

    return opening_suite[previous_seeded % len(opening_suite)]


def _target_seeded_game_count(total_games: int, seeded_start_fraction: float) -> int:
    clamped_games = max(total_games, 0)
    return min(clamped_games, max(0, math.floor((clamped_games * seeded_start_fraction) + 0.5)))


def _resolve_path_relative_to_config(config_path: str | Path, candidate: str | Path) -> Path:
    path = Path(candidate)
    if path.is_absolute():
        if not path.exists():
            raise ValueError(f"path does not exist: {path}")
        return path

    config_relative = (Path(config_path).resolve().parent / path).resolve()
    repo_relative = (Path.cwd() / path).resolve()

    if config_relative.exists() and repo_relative.exists() and config_relative != repo_relative:
        raise ValueError(
            "ambiguous relative path "
            f"{candidate!s}; both {config_relative} and {repo_relative} exist"
        )
    if config_relative.exists():
        return config_relative
    if repo_relative.exists():
        return repo_relative
    raise ValueError(
        "could not resolve path "
        f"{candidate!s}; tried {config_relative} and {repo_relative}"
    )


def _effective_relative_ply_cap(
    *,
    configured_limit: int,
    config: AppConfig,
    starting_ply: int,
) -> int | None:
    if configured_limit > 0:
        return starting_ply + configured_limit
    if config.game.is_bounded():
        return None
    raise ValueError("training.max_game_plies must be > 0 for unbounded boards")
