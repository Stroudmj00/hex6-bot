"""Dispatch standard Hex6 jobs from a Colab notebook or Drive-synced runtime."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

from hex6.integration import GPU_TIER_ORDER, detect_runtime_gpus, format_gpu_report, gpu_meets_minimum


def build_common_command(python_exe: str, module: str) -> list[str]:
    return [python_exe, "-m", module]


def resolve_repo_root(repo_root: str) -> Path:
    path = Path(repo_root).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"repo root does not exist: {path}")
    return path


def run_command(command: list[str], *, workdir: Path) -> int:
    print("Running:", " ".join(command))
    completed = subprocess.run(command, cwd=workdir, check=False)
    return int(completed.returncode)


def add_shared_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--python-exe",
        default=sys.executable,
        help="Python executable used to launch the repo module.",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Path to the repo root in the Colab runtime.",
    )
    parser.add_argument(
        "--status-backend",
        default=None,
        help="Override the configured status backend.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional explicit run id.",
    )
    parser.add_argument(
        "--minimum-gpu-tier",
        choices=GPU_TIER_ORDER[:-1],
        default=None,
        help="Fail fast unless the detected NVIDIA GPU is at least this tier.",
    )


def enforce_gpu_policy(args: argparse.Namespace) -> int:
    gpus = detect_runtime_gpus()
    print(format_gpu_report(gpus))
    if args.minimum_gpu_tier is None:
        return 0
    if not gpus:
        print(f"Rejected runtime: no NVIDIA GPU detected; require >= {args.minimum_gpu_tier}.")
        return 2
    primary = gpus[0]
    if gpu_meets_minimum(primary, args.minimum_gpu_tier):
        return 0
    print(
        "Rejected runtime: "
        f"detected {primary.name} [{primary.tier}] but require >= {args.minimum_gpu_tier}."
    )
    return 2


def cmd_bootstrap(args: argparse.Namespace) -> int:
    workdir = resolve_repo_root(args.repo_root)
    command = build_common_command(args.python_exe, "hex6.train.run_bootstrap")
    command.extend(["--config", args.config, "--output", args.output])
    if args.run_id:
        command.extend(["--run-id", args.run_id])
    if args.status_backend:
        command.extend(["--status-backend", args.status_backend])
    return run_command(command, workdir=workdir)


def cmd_cycle(args: argparse.Namespace) -> int:
    workdir = resolve_repo_root(args.repo_root)
    command = build_common_command(args.python_exe, "hex6.train.run_cycle")
    command.extend(["--config", args.config, "--output-root", args.output_root])
    if args.run_id:
        command.extend(["--run-id", args.run_id])
    if args.status_backend:
        command.extend(["--status-backend", args.status_backend])
    if args.minutes is not None:
        command.extend(["--minutes", str(args.minutes)])
    if args.cycles is not None:
        command.extend(["--cycles", str(args.cycles)])
    if args.start_checkpoint:
        command.extend(["--start-checkpoint", args.start_checkpoint])
    return run_command(command, workdir=workdir)


def cmd_tournament(args: argparse.Namespace) -> int:
    workdir = resolve_repo_root(args.repo_root)
    command = build_common_command(args.python_exe, "hex6.eval.run_tournament")
    command.extend(
        [
            "--config",
            args.config,
            "--output",
            args.output,
            "--games-per-match",
            str(args.games_per_match),
            "--max-game-plies",
            str(args.max_game_plies),
            "--max-checkpoints",
            str(args.max_checkpoints),
            "--checkpoint-glob",
            args.checkpoint_glob,
            "--random-seed",
            str(args.random_seed),
        ]
    )
    if args.opening_suite:
        command.extend(["--opening-suite", args.opening_suite])
    else:
        command.append("--no-opening-suite")
    if args.include_baseline:
        command.append("--include-baseline")
    else:
        command.append("--no-include-baseline")
    if args.include_random:
        command.append("--include-random")
    else:
        command.append("--no-include-random")
    if args.run_id:
        command.extend(["--run-id", args.run_id])
    if args.status_backend:
        command.extend(["--status-backend", args.status_backend])
    return run_command(command, workdir=workdir)


def cmd_queue(args: argparse.Namespace) -> int:
    workdir = resolve_repo_root(args.repo_root)
    command = build_common_command(args.python_exe, "hex6.integration.run_priority_loop")
    command.extend(["--queue", args.queue, "--state", args.state])
    if args.status_backend:
        command.extend(["--status-backend", args.status_backend])
    if args.once:
        command.append("--once")
    if args.dry_run:
        command.append("--dry-run")
    if args.max_jobs is not None:
        command.extend(["--max-jobs", str(args.max_jobs)])
    if args.max_minutes is not None:
        command.extend(["--max-minutes", str(args.max_minutes)])
    return run_command(command, workdir=workdir)


def cmd_runtime_benchmark(args: argparse.Namespace) -> int:
    workdir = resolve_repo_root(args.repo_root)
    command = build_common_command(args.python_exe, "hex6.train.benchmark_runtime")
    command.extend(["--config", args.config, "--output", args.output])
    for value in args.cpu_threads:
        command.extend(["--cpu-threads", str(value)])
    for value in args.interop_threads:
        command.extend(["--interop-threads", str(value)])
    for value in args.self_play_workers:
        command.extend(["--self-play-workers", str(value)])
    for value in args.data_loader_workers:
        command.extend(["--data-loader-workers", str(value)])
    for value in args.parallel_expansions_per_root:
        command.extend(["--parallel-expansions-per-root", str(value)])
    if args.root_simulations is not None:
        command.extend(["--root-simulations", str(args.root_simulations)])
    if args.bootstrap_games is not None:
        command.extend(["--bootstrap-games", str(args.bootstrap_games)])
    if args.epochs is not None:
        command.extend(["--epochs", str(args.epochs)])
    if args.max_game_plies is not None:
        command.extend(["--max-game-plies", str(args.max_game_plies)])
    if args.keep_artifacts:
        command.append("--keep-artifacts")
    return run_command(command, workdir=workdir)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run standard Hex6 jobs from Colab.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap", help="Run bootstrap training.")
    add_shared_run_args(bootstrap)
    bootstrap.add_argument("--config", default="configs/colab.toml")
    bootstrap.add_argument("--output", default="artifacts/bootstrap_colab")
    bootstrap.set_defaults(handler=cmd_bootstrap)

    cycle = subparsers.add_parser("cycle", help="Run repeated self-play cycles.")
    add_shared_run_args(cycle)
    cycle.add_argument("--config", default="configs/colab_strongest_v2.toml")
    cycle.add_argument("--output-root", default="artifacts/bootstrap_colab_strongest_v2")
    cycle.add_argument("--minutes", type=float, default=60.0)
    cycle.add_argument("--cycles", type=int, default=None)
    cycle.add_argument("--start-checkpoint", default=None)
    cycle.set_defaults(handler=cmd_cycle)

    tournament = subparsers.add_parser("tournament", help="Run tournament evaluation.")
    add_shared_run_args(tournament)
    tournament.add_argument("--config", default="configs/fast.toml")
    tournament.add_argument("--output", default="artifacts/tournament_colab")
    tournament.add_argument("--games-per-match", type=int, default=4)
    tournament.add_argument("--max-game-plies", type=int, default=0)
    tournament.add_argument("--max-checkpoints", type=int, default=3)
    tournament.add_argument("--checkpoint-glob", default="artifacts/**/bootstrap_model.pt")
    tournament.add_argument("--opening-suite", default="configs/experiments/conversion_opening_suite.toml")
    tournament.add_argument("--include-baseline", action="store_true", default=True)
    tournament.add_argument("--no-include-baseline", dest="include_baseline", action="store_false")
    tournament.add_argument("--include-random", action="store_true", default=True)
    tournament.add_argument("--no-include-random", dest="include_random", action="store_false")
    tournament.add_argument("--random-seed", type=int, default=7)
    tournament.set_defaults(handler=cmd_tournament)

    queue = subparsers.add_parser("queue", help="Run the Colab priority loop.")
    add_shared_run_args(queue)
    queue.add_argument("--queue", default="configs/colab_job_queue.toml")
    queue.add_argument("--state", default="artifacts/colab_queue/state.json")
    queue.add_argument("--once", action="store_true")
    queue.add_argument("--dry-run", action="store_true")
    queue.add_argument("--max-jobs", type=int, default=None)
    queue.add_argument("--max-minutes", type=float, default=None)
    queue.set_defaults(handler=cmd_queue)

    runtime_benchmark = subparsers.add_parser("runtime-benchmark", help="Run runtime/parallelism benchmark sweeps.")
    add_shared_run_args(runtime_benchmark)
    runtime_benchmark.add_argument("--config", default="configs/colab_strongest_v2.toml")
    runtime_benchmark.add_argument("--output", default="artifacts/runtime_parallelism_colab")
    runtime_benchmark.add_argument("--cpu-threads", nargs="+", type=int, default=[8])
    runtime_benchmark.add_argument("--interop-threads", nargs="+", type=int, default=[2])
    runtime_benchmark.add_argument("--self-play-workers", nargs="+", type=int, default=[4, 8, 12])
    runtime_benchmark.add_argument("--data-loader-workers", nargs="+", type=int, default=[2])
    runtime_benchmark.add_argument("--parallel-expansions-per-root", nargs="+", type=int, default=[4, 6, 8])
    runtime_benchmark.add_argument("--root-simulations", type=int, default=96)
    runtime_benchmark.add_argument("--bootstrap-games", type=int, default=2)
    runtime_benchmark.add_argument("--epochs", type=int, default=1)
    runtime_benchmark.add_argument("--max-game-plies", type=int, default=0)
    runtime_benchmark.add_argument("--keep-artifacts", action="store_true")
    runtime_benchmark.set_defaults(handler=cmd_runtime_benchmark)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    gate_exit = enforce_gpu_policy(args)
    if gate_exit != 0:
        raise SystemExit(gate_exit)
    raise SystemExit(args.handler(args))


if __name__ == "__main__":
    main()
