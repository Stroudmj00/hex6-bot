"""Bootstrap training loop using search-generated self-play."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
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
    search = BaselineTurnSearch()
    examples: list[BootstrapExample] = []

    for game_index in range(config.training.bootstrap_games):
        state = GameState.initial(config.game)
        trajectory: list[tuple[GameState, Coord]] = []

        while not state.is_terminal and state.ply_count < config.training.max_game_plies:
            turn = search.choose_turn(state, config)
            trajectory.append((state, turn.cells[0]))
            state = search.apply_cells(state, turn.cells, config)

        winner = state.winner
        print(
            f"[self-play] game {game_index + 1}/{config.training.bootstrap_games} "
            f"completed: plies={state.ply_count} winner={winner or 'draw'}"
        )
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

        if progress_path is not None or progress_callback is not None:
            _emit_progress(
                progress_path,
                progress_callback,
                {
                    "stage": "self_play",
                    "completed_games": game_index + 1,
                    "total_games": config.training.bootstrap_games,
                    "examples_so_far": len(examples),
                    "last_winner": winner,
                    "last_game_plies": state.ply_count,
                },
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
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    progress_path = output_path / "progress.json"
    _emit_progress(progress_path, progress_callback, {"stage": "starting"})

    examples = generate_bootstrap_examples_with_progress(config, progress_path, progress_callback)
    dataset = BootstrapDataset(examples, config)
    loader = DataLoader(dataset, batch_size=config.training.batch_size, shuffle=True)
    _emit_progress(
        progress_path,
        progress_callback,
        {
            "stage": "dataset_ready",
            "examples": len(examples),
            "encoded_examples": len(dataset),
        },
    )

    device = _select_device(config)
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
    for epoch in range(config.training.epochs):
        policy_total = 0.0
        value_total = 0.0
        batch_count = 0

        for batch_inputs, batch_policy, batch_value in loader:
            batch_inputs = batch_inputs.to(device)
            batch_policy = batch_policy.to(device)
            batch_value = batch_value.to(device)

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

    checkpoint_path = output_path / "bootstrap_model.pt"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "config_path": config_path,
            "history": history,
        },
        checkpoint_path,
    )

    metrics = {
        "device": str(device),
        "examples": len(examples),
        "encoded_examples": len(dataset),
        "epochs": config.training.epochs,
        "final_policy_loss": history[-1]["policy_loss"],
        "final_value_loss": history[-1]["value_loss"],
        "checkpoint": str(checkpoint_path),
    }
    if init_checkpoint_path is not None:
        metrics["init_checkpoint"] = str(init_checkpoint_path)

    with (output_path / "metrics.json").open("w", encoding="ascii") as handle:
        json.dump(metrics, handle, indent=2)
    _emit_progress(progress_path, progress_callback, {"stage": final_stage, **metrics})

    return metrics


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
