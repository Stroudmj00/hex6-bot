"""Small policy/value network for bootstrap training."""

from __future__ import annotations

import torch
from torch import nn


class ResidualBlock(nn.Module):
    def __init__(self, channels: int) -> None:
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(channels, channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(channels, channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(channels),
        )
        self.activation = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.activation(x + self.block(x))


class HexPolicyValueNet(nn.Module):
    def __init__(self, input_channels: int = 6, channels: int = 64, blocks: int = 8) -> None:
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv2d(input_channels, channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(channels),
            nn.ReLU(inplace=True),
        )
        self.backbone = nn.Sequential(*(ResidualBlock(channels) for _ in range(blocks)))
        self.policy_head = nn.Conv2d(channels, 1, kernel_size=1)
        self.value_head = nn.Sequential(
            nn.Conv2d(channels, channels // 2, kernel_size=1),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Linear(channels // 2, channels // 2),
            nn.ReLU(inplace=True),
            nn.Linear(channels // 2, 1),
            nn.Tanh(),
        )

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        features = self.backbone(self.stem(x))
        policy_logits = self.policy_head(features).flatten(start_dim=1)
        value = self.value_head(features).squeeze(-1)
        return policy_logits, value


def load_compatible_state_dict(
    model: nn.Module,
    state_dict: dict[str, torch.Tensor],
) -> dict[str, int]:
    """Load only tensors whose names and shapes still match."""
    target_state = model.state_dict()
    compatible = {
        key: value
        for key, value in state_dict.items()
        if key in target_state and target_state[key].shape == value.shape
    }
    missing = len(target_state) - len(compatible)
    skipped = len(state_dict) - len(compatible)
    model.load_state_dict(compatible, strict=False)
    return {
        "loaded_tensors": len(compatible),
        "missing_tensors": missing,
        "skipped_tensors": skipped,
        "total_target_tensors": len(target_state),
        "total_source_tensors": len(state_dict),
    }
