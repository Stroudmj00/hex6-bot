"""Benchmark bootstrap training throughput across runtime settings."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from itertools import product
from pathlib import Path
import shutil
from typing import Any

from hex6.config import AppConfig, load_config
from hex6.train.bootstrap import train_bootstrap


def build_variant(
    config: AppConfig,
    *,
    cpu_threads: int,
    interop_threads: int,
    self_play_workers: int,
    data_loader_workers: int,
    bootstrap_games: int | None,
    epochs: int | None,
    max_game_plies: int | None,
) -> AppConfig:
    runtime = replace(
        config.runtime,
        cpu_threads=cpu_threads,
        interop_threads=interop_threads,
    )
    training = replace(
        config.training,
        self_play_workers=self_play_workers,
        data_loader_workers=data_loader_workers,
        bootstrap_games=bootstrap_games if bootstrap_games is not None else config.training.bootstrap_games,
        epochs=epochs if epochs is not None else config.training.epochs,
        max_game_plies=max_game_plies if max_game_plies is not None else config.training.max_game_plies,
    )
    evaluation = replace(config.evaluation, arena_games=0)
    return replace(config, runtime=runtime, training=training, evaluation=evaluation)


def summarize_variant(config: AppConfig) -> dict[str, Any]:
    return {
        "cpu_threads": config.runtime.cpu_threads,
        "interop_threads": config.runtime.interop_threads,
        "self_play_workers": config.training.self_play_workers,
        "data_loader_workers": config.training.data_loader_workers,
        "bootstrap_games": config.training.bootstrap_games,
        "epochs": config.training.epochs,
        "max_game_plies": config.training.max_game_plies,
    }


def benchmark_runtime(
    *,
    config: AppConfig,
    output_dir: Path,
    config_path: str,
    cpu_threads: list[int],
    interop_threads: list[int],
    self_play_workers: list[int],
    data_loader_workers: list[int],
    bootstrap_games: int | None,
    epochs: int | None,
    max_game_plies: int | None,
    keep_artifacts: bool,
) -> dict[str, Any]:
    if len(interop_threads) != 1:
        raise ValueError("Benchmark one interop thread count per invocation; PyTorch interop threads cannot be safely retuned mid-process.")

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    for index, (cpu_thread_count, interop_thread_count, self_play_worker_count, data_loader_worker_count) in enumerate(
        product(cpu_threads, interop_threads, self_play_workers, data_loader_workers),
        start=1,
    ):
        variant = build_variant(
            config,
            cpu_threads=cpu_thread_count,
            interop_threads=interop_thread_count,
            self_play_workers=self_play_worker_count,
            data_loader_workers=data_loader_worker_count,
            bootstrap_games=bootstrap_games,
            epochs=epochs,
            max_game_plies=max_game_plies,
        )
        run_dir = output_dir / (
            f"run_{index:02d}_cpu{cpu_thread_count}_interop{interop_thread_count}"
            f"_sp{self_play_worker_count}_dl{data_loader_worker_count}"
        )
        metrics = train_bootstrap(
            config=variant,
            output_dir=run_dir,
            config_path=config_path,
            final_stage="complete",
        )
        result = {
            "run_index": index,
            "variant": summarize_variant(variant),
            "metrics": metrics,
        }
        results.append(result)
        print(json.dumps(result, indent=2))
        if not keep_artifacts:
            shutil.rmtree(run_dir, ignore_errors=True)

    ranked = sorted(results, key=lambda item: float(item["metrics"]["total_seconds"]))
    summary = {
        "base_config": config_path,
        "benchmark_count": len(results),
        "results": results,
        "ranked_by_total_seconds": [
            {
                "run_index": item["run_index"],
                "variant": item["variant"],
                "total_seconds": item["metrics"]["total_seconds"],
                "self_play_seconds": item["metrics"]["self_play_seconds"],
                "training_seconds": item["metrics"]["training_seconds"],
                "self_play_examples_per_second": item["metrics"]["self_play_examples_per_second"],
                "training_examples_per_second": item["metrics"]["training_examples_per_second"],
            }
            for item in ranked
        ],
        "best_variant": ranked[0]["variant"] if ranked else None,
        "best_metrics": ranked[0]["metrics"] if ranked else None,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="ascii")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark bootstrap runtime settings.")
    parser.add_argument("--config", default="configs/default.toml", help="Base config path.")
    parser.add_argument("--output", default="artifacts/runtime_benchmark", help="Benchmark output directory.")
    parser.add_argument(
        "--cpu-threads",
        nargs="+",
        type=int,
        default=[8, 12],
        help="CPU thread counts to benchmark.",
    )
    parser.add_argument(
        "--interop-threads",
        nargs="+",
        type=int,
        default=[2],
        help="Interop thread counts to benchmark. Use one value per run.",
    )
    parser.add_argument(
        "--self-play-workers",
        nargs="+",
        type=int,
        default=[1, 2, 4],
        help="Self-play worker counts to benchmark.",
    )
    parser.add_argument(
        "--data-loader-workers",
        nargs="+",
        type=int,
        default=[0, 2],
        help="DataLoader worker counts to benchmark.",
    )
    parser.add_argument("--bootstrap-games", type=int, default=2, help="Override bootstrap game count.")
    parser.add_argument("--epochs", type=int, default=1, help="Override epoch count.")
    parser.add_argument("--max-game-plies", type=int, default=8, help="Override max game plies.")
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Keep per-run checkpoint artifacts instead of deleting them after each run.",
    )
    args = parser.parse_args()

    summary = benchmark_runtime(
        config=load_config(args.config),
        output_dir=Path(args.output),
        config_path=args.config,
        cpu_threads=args.cpu_threads,
        interop_threads=args.interop_threads,
        self_play_workers=args.self_play_workers,
        data_loader_workers=args.data_loader_workers,
        bootstrap_games=args.bootstrap_games,
        epochs=args.epochs,
        max_game_plies=args.max_game_plies,
        keep_artifacts=args.keep_artifacts,
    )
    print(json.dumps(summary["ranked_by_total_seconds"], indent=2))


if __name__ == "__main__":
    main()
