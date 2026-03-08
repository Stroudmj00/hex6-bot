"""Bootstrap training loop using search-generated self-play."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
import json
import multiprocessing as mp
import os
from pathlib import Path
import time
from typing import Callable

import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from hex6.config import AppConfig, load_config
from hex6.game import Coord, GameState
from hex6.game.symmetry import rotate_coord, rotate_state
from hex6.nn import HexPolicyValueNet, cell_to_policy_index, encode_state
from hex6.search import BaselineTurnSearch


@dataclass(frozen=True)
class BootstrapExample:
    state: GameState
    target_cell: Coord
    value_target: float


@dataclass(frozen=True)
class BootstrapGameResult:
    game_index: int
    winner: str | None
    plies: int
    examples: tuple[BootstrapExample, ...]


class BootstrapDataset(Dataset[tuple[torch.Tensor, torch.Tensor, torch.Tensor]]):
    def __init__(self, examples: list[BootstrapExample], config: AppConfig) -> None:
        inputs: list[torch.Tensor] = []
        policy_targets: list[int] = []
        value_targets: list[float] = []

        for example in examples:
            encoded = encode_state(example.state, config)
            policy_index = cell_to_policy_index(encoded, example.target_cell)
            if policy_index is None:
                continue
            inputs.append(encoded.tensor)
            policy_targets.append(policy_index)
            value_targets.append(example.value_target)

        if not inputs:
            raise ValueError("bootstrap dataset is empty after encoding")

        self.inputs = torch.stack(inputs)
        self.policy_targets = torch.tensor(policy_targets, dtype=torch.long)
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


def generate_bootstrap_examples(config: AppConfig) -> list[BootstrapExample]:
    return generate_bootstrap_examples_with_progress(config)


def generate_bootstrap_examples_with_progress(
    config: AppConfig,
    progress_path: Path | None = None,
    progress_callback: ProgressCallback | None = None,
) -> list[BootstrapExample]:
    examples: list[BootstrapExample] = []
    total_games = config.training.bootstrap_games
    workers = max(1, min(config.training.self_play_workers, total_games))

    if workers == 1 or total_games <= 1:
        for game_index in range(total_games):
            result = _generate_bootstrap_game(game_index, config)
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
        futures = [executor.submit(_generate_bootstrap_game, game_index, config) for game_index in range(total_games)]
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
) -> dict[str, float | int | str]:
    config = config or load_config()
    configure_runtime(config)
    overall_started = time.perf_counter()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    progress_path = output_path / "progress.json"
    _emit_progress(progress_path, progress_callback, {"stage": "starting"})

    self_play_started = time.perf_counter()
    examples = generate_bootstrap_examples_with_progress(config, progress_path, progress_callback)
    self_play_seconds = round(time.perf_counter() - self_play_started, 3)

    dataset_started = time.perf_counter()
    dataset = BootstrapDataset(examples, config)
    device = _select_device(config)
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
            "encoded_examples": len(dataset),
            "self_play_seconds": self_play_seconds,
            "dataset_seconds": dataset_seconds,
        },
    )

    model = HexPolicyValueNet(
        input_channels=6,
        channels=config.model.channels,
        blocks=config.model.blocks,
    ).to(device)
    if init_checkpoint_path is not None:
        checkpoint = torch.load(init_checkpoint_path, map_location=device)
        model.load_state_dict(checkpoint["model_state_dict"])

    optimizer = torch.optim.AdamW(model.parameters(), lr=config.training.learning_rate)
    policy_loss_fn = nn.CrossEntropyLoss()
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
                policy_loss = policy_loss_fn(policy_logits, batch_policy)
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
    metrics = {
        "device": str(device),
        "examples": len(examples),
        "encoded_examples": len(dataset),
        "epochs": config.training.epochs,
        "final_policy_loss": history[-1]["policy_loss"],
        "final_value_loss": history[-1]["value_loss"],
        "checkpoint": str(checkpoint_path),
        "self_play_seconds": self_play_seconds,
        "dataset_seconds": dataset_seconds,
        "training_seconds": training_seconds,
        "total_seconds": total_seconds,
        "self_play_examples_per_second": round(len(examples) / max(self_play_seconds, 1e-9), 3),
        "training_examples_per_second": round((len(dataset) * config.training.epochs) / max(training_seconds, 1e-9), 3),
        "self_play_workers": config.training.self_play_workers,
        "data_loader_workers": config.training.data_loader_workers,
        "cpu_threads": torch.get_num_threads(),
        "interop_threads": torch.get_num_interop_threads(),
    }
    if init_checkpoint_path is not None:
        metrics["init_checkpoint"] = str(init_checkpoint_path)

    with (output_path / "metrics.json").open("w", encoding="ascii") as handle:
        json.dump(metrics, handle, indent=2)
    _emit_progress(progress_path, progress_callback, {"stage": final_stage, **metrics})

    return metrics


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
        f"completed: plies={result.plies} winner={result.winner or 'draw'}"
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
            },
        )


def _generate_bootstrap_game(game_index: int, config: AppConfig) -> BootstrapGameResult:
    search = BaselineTurnSearch()
    state = GameState.initial(config.game)
    trajectory: list[tuple[GameState, Coord]] = []

    while not state.is_terminal and state.ply_count < config.training.max_game_plies:
        turn = search.choose_turn(state, config)
        trajectory.append((state, turn.cells[0]))
        state = search.apply_cells(state, turn.cells, config)

    winner = state.winner
    examples: list[BootstrapExample] = []
    for position, target_cell in trajectory:
        value_target = 0.0 if winner is None else (1.0 if position.to_play == winner else -1.0)
        examples.append(BootstrapExample(position, target_cell, value_target))

        if config.training.symmetry_augmentation:
            for steps in range(1, 6):
                examples.append(
                    BootstrapExample(
                        state=rotate_state(position, steps),
                        target_cell=rotate_coord(target_cell, steps),
                        value_target=value_target,
                    )
                )

    return BootstrapGameResult(
        game_index=game_index,
        winner=winner,
        plies=state.ply_count,
        examples=tuple(examples),
    )


def _self_play_mp_context() -> mp.context.BaseContext:
    if os.name == "nt":
        return mp.get_context("spawn")
    return mp.get_context("fork")
