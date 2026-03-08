"""Config-driven search variant arena runner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import time
import tomllib
from typing import Any, Callable

from hex6.config import AppConfig, apply_overrides, load_config_mapping
from hex6.eval.arena import AgentSpec, run_arena
from hex6.eval.openings import OpeningScenario, load_opening_suite
from hex6.search import BaselineTurnSearch


@dataclass(frozen=True)
class SearchVariantSpec:
    name: str
    description: str
    overrides: dict[str, Any]


@dataclass(frozen=True)
class SearchMatrixSpec:
    base_path: Path
    base_config: AppConfig
    games: int
    opening_suite: tuple[OpeningScenario, ...]
    variants: tuple[SearchVariantSpec, ...]


SearchMatrixProgressCallback = Callable[[dict[str, object]], None]


def load_search_matrix(path: str | Path) -> SearchMatrixSpec:
    matrix_path = Path(path)
    with matrix_path.open("rb") as handle:
        data = tomllib.load(handle)

    base_path = resolved_base_config_path(matrix_path, data["base_config"])
    base_mapping = load_config_mapping(base_path)
    base_overrides = data.get("base_overrides", {})
    if base_overrides:
        base_mapping = apply_overrides(base_mapping, base_overrides)
    base_config = AppConfig.from_mapping(base_mapping)
    games = int(data.get("games", base_config.evaluation.arena_games or 2))
    opening_suite_path = data.get("opening_suite")
    opening_suite = (
        tuple(load_opening_suite(resolved_relative_path(matrix_path, opening_suite_path), base_config))
        if opening_suite_path
        else ()
    )
    variants = tuple(
        SearchVariantSpec(
            name=entry["name"],
            description=entry.get("description", ""),
            overrides=entry.get("overrides", {}),
        )
        for entry in data["variants"]
    )
    return SearchMatrixSpec(
        base_path=base_path,
        base_config=base_config,
        games=games,
        opening_suite=opening_suite,
        variants=variants,
    )


def run_search_variant_matrix(
    matrix_path: str | Path,
    *,
    output_dir: str | Path,
    progress_callback: SearchMatrixProgressCallback | None = None,
) -> dict[str, object]:
    spec = load_search_matrix(matrix_path)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    baseline_agent = build_search_agent("baseline", spec.base_config)
    results: list[dict[str, object]] = []
    total_variants = len(spec.variants)

    base_mapping = load_config_mapping(spec.base_path)
    with Path(matrix_path).open("rb") as handle:
        matrix_data = tomllib.load(handle)
    base_overrides = matrix_data.get("base_overrides", {})
    if base_overrides:
        base_mapping = apply_overrides(base_mapping, base_overrides)

    if progress_callback is not None:
        progress_callback(
            {
                "stage": "search_matrix",
                "completed_variants": 0,
                "total_variants": total_variants,
                "matrix_path": str(matrix_path),
                "base_config": str(spec.base_path),
            }
        )

    for index, variant in enumerate(spec.variants, start=1):
        variant_mapping = apply_overrides(base_mapping, variant.overrides)
        variant_config = AppConfig.from_mapping(variant_mapping)
        agent = build_search_agent(variant.name, variant_config)
        started = time.perf_counter()
        arena = run_arena(
            agent_a=agent,
            agent_b=baseline_agent,
            config=variant_config,
            games=spec.games,
            opening_suite=list(spec.opening_suite) if spec.opening_suite else None,
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
        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "search_matrix",
                    "completed_variants": index,
                    "total_variants": total_variants,
                    "current_variant": variant.name,
                    "elapsed_seconds": elapsed,
                    "elo_delta": arena["elo_delta_a"],
                    "win_rate": arena["win_rate_a"],
                    "wins": arena["wins_a"],
                    "losses": arena["wins_b"],
                    "draws": arena["draws"],
                }
            )

    results.sort(key=lambda item: (item["elo_delta"], item["win_rate"]), reverse=True)
    summary = {
        "matrix_path": str(matrix_path),
        "base_config": str(spec.base_path),
        "games_per_match": spec.games,
        "opening_suite_size": len(spec.opening_suite),
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


def resolved_base_config_path(matrix_path: str | Path, base_config_reference: str) -> Path:
    matrix_file = Path(matrix_path)
    return (matrix_file.parent / base_config_reference).resolve()


def resolved_relative_path(matrix_path: str | Path, reference: str | None) -> Path:
    if reference is None:
        raise ValueError("relative path reference is missing")
    matrix_file = Path(matrix_path)
    return (matrix_file.parent / reference).resolve()
