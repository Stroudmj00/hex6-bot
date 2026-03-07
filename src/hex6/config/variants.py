"""Config override helpers for experiment matrices."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tomllib
from typing import Any

from .schema import AppConfig


def load_config_mapping(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    with config_path.open("rb") as handle:
        return tomllib.load(handle)


def apply_overrides(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    _merge_in_place(merged, overrides)
    return merged


def load_config_with_overrides(
    base_path: str | Path,
    overrides: dict[str, Any],
) -> AppConfig:
    base = load_config_mapping(base_path)
    merged = apply_overrides(base, overrides)
    return AppConfig.from_mapping(merged)


def _merge_in_place(target: dict[str, Any], overrides: dict[str, Any]) -> None:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_in_place(target[key], value)
        else:
            target[key] = value
