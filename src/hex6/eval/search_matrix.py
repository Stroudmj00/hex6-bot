"""Config-driven search variant arena runner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import time
import tomllib
from typing import Any

from hex6.config import AppConfig, load_config, load_config_with_overrides
from hex6.eval.arena import AgentSpec, run_arena
from hex6.search import BaselineTurnSearch


@dataclass(frozen=True)
class SearchVariantSpec:
    name: str
    description: str
    overrides: dict[str, Any]


def load_search_matrix(path: str | Path) -> tuple[AppConfig, int, list[SearchVariantSpec]]:
    matrix_path = Path(path)
    with matrix_path.open("rb") as handle:
        data = tomllib.load(handle)

    base_path = resolved_base_config_path(matrix_path, data["base_config"])
    base_config = load_config(base_path)
    games = int(data.get("games", base_config.evaluation.arena_games or 2))
    variants = [
        SearchVariantSpec(
            name=entry["name"],
            description=entry.get("description", ""),
            overrides=entry.get("overrides", {}),
        )
        for entry in data["variants"]
    ]
    return base_config, games, variants


def run_search_variant_matrix(
    matrix_path: str | Path,
    *,
    output_dir: str | Path,
) -> dict[str, object]:
    base_config, games, variants = load_search_matrix(matrix_path)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    baseline_agent = build_search_agent("baseline", base_config)
    results: list[dict[str, object]] = []
    base_path = resolved_base_config_path(matrix_path, read_base_config_reference(matrix_path))

    for variant in variants:
        variant_config = load_config_with_overrides(base_path, variant.overrides)
        agent = build_search_agent(variant.name, variant_config)
        started = time.perf_counter()
        arena = run_arena(
            agent_a=agent,
            agent_b=baseline_agent,
            config=variant_config,
            games=games,
        )
        elapsed = round(time.perf_counter() - started, 2)
        result = {
            "name": variant.name,
            "description": variant.description,
            "elapsed_seconds": elapsed,
            "elo_delta": arena["elo_delta_a"],
            "win_rate": arena["win_rate_a"],
            "wins": arena["wins_a"],
            "losses": arena["wins_b"],
            "draws": arena["draws"],
            "arena": arena,
            "overrides": variant.overrides,
        }
        results.append(result)
        (output_path / f"{variant.name}.json").write_text(json.dumps(result, indent=2), encoding="ascii")

    results.sort(key=lambda item: (item["elo_delta"], item["win_rate"]), reverse=True)
    summary = {
        "matrix_path": str(matrix_path),
        "base_config": str(base_path),
        "games_per_match": games,
        "results": results,
        "best_variant": results[0]["name"] if results else None,
    }
    (output_path / "summary.json").write_text(json.dumps(summary, indent=2), encoding="ascii")
    return summary


def build_search_agent(name: str, config: AppConfig) -> AgentSpec:
    search = BaselineTurnSearch()
    return AgentSpec(
        name=name,
        kind="search_variant",
        choose_turn=lambda state, _arena_config: search.choose_turn(state, config),
    )


def read_base_config_reference(matrix_path: str | Path) -> str:
    matrix_file = Path(matrix_path)
    with matrix_file.open("rb") as handle:
        data = tomllib.load(handle)
    return str(data["base_config"])


def resolved_base_config_path(matrix_path: str | Path, base_config_reference: str) -> Path:
    matrix_file = Path(matrix_path)
    return (matrix_file.parent / base_config_reference).resolve()
