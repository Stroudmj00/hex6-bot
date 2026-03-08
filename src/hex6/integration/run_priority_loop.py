"""Priority-based Colab job loop to keep the GPU lane busy."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import time
import tomllib
from typing import Any


@dataclass(frozen=True)
class QueueConfig:
    name: str
    idle_sleep_seconds: float
    post_job_pause_seconds: float
    default_status_backend: str
    default_run_prefix: str
    jobs: tuple["JobSpec", ...]


@dataclass(frozen=True)
class JobSpec:
    job_id: str
    kind: str
    priority: int
    enabled: bool
    min_interval_minutes: float
    options: dict[str, Any]


def load_queue_config(path: str | Path) -> QueueConfig:
    queue_path = Path(path)
    with queue_path.open("rb") as handle:
        data = tomllib.load(handle)

    queue_table = data.get("queue", {})
    jobs_table = data.get("jobs", [])
    jobs: list[JobSpec] = []
    for row in jobs_table:
        job_id = str(row["id"]).strip()
        kind = str(row["kind"]).strip()
        priority = int(row["priority"])
        enabled = bool(row.get("enabled", True))
        min_interval_minutes = float(row.get("min_interval_minutes", 0.0))
        options = {k: v for k, v in row.items() if k not in {"id", "kind", "priority", "enabled", "min_interval_minutes"}}
        jobs.append(
            JobSpec(
                job_id=job_id,
                kind=kind,
                priority=priority,
                enabled=enabled,
                min_interval_minutes=max(min_interval_minutes, 0.0),
                options=options,
            )
        )

    if not jobs:
        raise ValueError(f"queue config has no jobs: {queue_path}")

    return QueueConfig(
        name=str(queue_table.get("name", "colab_priority_queue")),
        idle_sleep_seconds=max(float(queue_table.get("idle_sleep_seconds", 30.0)), 1.0),
        post_job_pause_seconds=max(float(queue_table.get("post_job_pause_seconds", 10.0)), 0.0),
        default_status_backend=str(queue_table.get("default_status_backend", "github_branch")),
        default_run_prefix=str(queue_table.get("default_run_prefix", "colabq")),
        jobs=tuple(jobs),
    )


def read_state(path: str | Path) -> dict[str, Any]:
    state_path = Path(path)
    if not state_path.exists():
        return {"jobs": {}, "history": []}
    return json.loads(state_path.read_text(encoding="ascii"))


def write_state(path: str | Path, payload: dict[str, Any]) -> None:
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, indent=2), encoding="ascii")


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_text(moment: datetime | None = None) -> str:
    dt = moment or utc_now()
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_run_id(prefix: str, job_id: str, now: datetime | None = None) -> str:
    moment = now or utc_now()
    suffix = moment.strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{job_id}-{suffix}"


def ensure_job_state(state: dict[str, Any], job_id: str) -> dict[str, Any]:
    jobs = state.setdefault("jobs", {})
    job_state = jobs.setdefault(
        job_id,
        {
            "runs": 0,
            "successes": 0,
            "failures": 0,
            "last_started_at": "",
            "last_completed_at": "",
            "last_success_at": "",
            "last_failed_at": "",
            "last_exit_code": None,
            "last_run_id": "",
        },
    )
    return job_state


def next_allowed_at(job: JobSpec, state: dict[str, Any]) -> datetime | None:
    job_state = ensure_job_state(state, job.job_id)
    anchor = parse_utc(job_state.get("last_completed_at"))
    if anchor is None:
        return None
    return anchor + timedelta(minutes=job.min_interval_minutes)


def choose_next_job(queue: QueueConfig, state: dict[str, Any], now: datetime | None = None) -> tuple[JobSpec | None, float]:
    moment = now or utc_now()
    eligible: list[tuple[int, datetime, JobSpec]] = []
    blocked_waits: list[float] = []
    scheduler_state = state.get("scheduler", {})
    last_job_id = str(scheduler_state.get("last_job_id", ""))
    consecutive_runs = int(scheduler_state.get("consecutive_runs", 0))

    for job in queue.jobs:
        if not job.enabled:
            continue
        gate = next_allowed_at(job, state)
        if gate is not None and gate > moment:
            blocked_waits.append((gate - moment).total_seconds())
            continue
        job_state = ensure_job_state(state, job.job_id)
        last_started = parse_utc(job_state.get("last_started_at")) or datetime.fromtimestamp(0, tz=timezone.utc)
        eligible.append((-job.priority, last_started, job))

    if eligible:
        eligible.sort(key=lambda item: (item[0], item[1]))
        selected = eligible[0][2]
        max_consecutive = max(1, int(selected.options.get("max_consecutive_runs", 1)))
        if selected.job_id == last_job_id and consecutive_runs >= max_consecutive and len(eligible) > 1:
            selected = eligible[1][2]
        return selected, 0.0

    if blocked_waits:
        return None, max(1.0, min(blocked_waits))
    return None, queue.idle_sleep_seconds


def build_job_command(job: JobSpec, python_exe: str, run_id: str, status_backend: str) -> list[str]:
    kind = job.kind
    o = job.options
    if kind == "bootstrap":
        return [
            python_exe,
            "-m",
            "hex6.train.run_bootstrap",
            "--config",
            str(o.get("config", "configs/colab.toml")),
            "--output",
            str(o.get("output", "artifacts/bootstrap_colab")),
            "--run-id",
            run_id,
            "--status-backend",
            status_backend,
        ]

    if kind == "cycle":
        command = [
            python_exe,
            "-m",
            "hex6.train.run_cycle",
            "--config",
            str(o.get("config", "configs/colab_hour.toml")),
            "--output-root",
            str(o.get("output_root", "artifacts/bootstrap_colab_hour")),
            "--run-id",
            run_id,
            "--status-backend",
            status_backend,
        ]
        if "minutes" in o:
            command.extend(["--minutes", str(o["minutes"])])
        if "cycles" in o:
            command.extend(["--cycles", str(o["cycles"])])
        if "start_checkpoint" in o:
            command.extend(["--start-checkpoint", str(o["start_checkpoint"])])
        if "minutes" not in o and "cycles" not in o:
            command.extend(["--minutes", "60"])
        return command

    if kind == "search_matrix":
        return [
            python_exe,
            "-m",
            "hex6.eval.run_search_matrix",
            "--matrix",
            str(o.get("matrix", "configs/experiments/search_matrix.toml")),
            "--output",
            str(o.get("output", "artifacts/search_matrix_colab")),
            "--run-id",
            run_id,
            "--status-backend",
            status_backend,
        ]

    if kind == "tournament":
        command = [
            python_exe,
            "-m",
            "hex6.eval.run_tournament",
            "--config",
            str(o.get("config", "configs/fast.toml")),
            "--output",
            str(o.get("output", "artifacts/tournament_colab")),
            "--games-per-match",
            str(o.get("games_per_match", 2)),
            "--max-game-plies",
            str(o.get("max_game_plies", 100)),
            "--max-checkpoints",
            str(o.get("max_checkpoints", 3)),
            "--checkpoint-glob",
            str(o.get("checkpoint_glob", "artifacts/**/bootstrap_model.pt")),
            "--random-seed",
            str(o.get("random_seed", 7)),
            "--run-id",
            run_id,
            "--status-backend",
            status_backend,
        ]
        include_baseline = bool(o.get("include_baseline", True))
        include_random = bool(o.get("include_random", True))
        if not include_baseline:
            command.append("--no-include-baseline")
        if not include_random:
            command.append("--no-include-random")
        return command

    raise ValueError(f"unsupported job kind: {kind}")


def update_state_started(state: dict[str, Any], job: JobSpec, run_id: str, now: datetime) -> None:
    job_state = ensure_job_state(state, job.job_id)
    job_state["runs"] = int(job_state.get("runs", 0)) + 1
    job_state["last_started_at"] = utc_text(now)
    job_state["last_run_id"] = run_id
    state["updated_at"] = utc_text(now)


def update_state_completed(
    state: dict[str, Any],
    job: JobSpec,
    run_id: str,
    started_at: datetime,
    completed_at: datetime,
    exit_code: int,
) -> None:
    job_state = ensure_job_state(state, job.job_id)
    job_state["last_completed_at"] = utc_text(completed_at)
    job_state["last_exit_code"] = exit_code
    if exit_code == 0:
        job_state["successes"] = int(job_state.get("successes", 0)) + 1
        job_state["last_success_at"] = utc_text(completed_at)
    else:
        job_state["failures"] = int(job_state.get("failures", 0)) + 1
        job_state["last_failed_at"] = utc_text(completed_at)

    history = state.setdefault("history", [])
    history.append(
        {
            "run_id": run_id,
            "job_id": job.job_id,
            "kind": job.kind,
            "priority": job.priority,
            "started_at": utc_text(started_at),
            "completed_at": utc_text(completed_at),
            "duration_seconds": round((completed_at - started_at).total_seconds(), 3),
            "exit_code": exit_code,
        }
    )
    if len(history) > 200:
        del history[: len(history) - 200]

    scheduler = state.setdefault("scheduler", {})
    if str(scheduler.get("last_job_id", "")) == job.job_id:
        scheduler["consecutive_runs"] = int(scheduler.get("consecutive_runs", 0)) + 1
    else:
        scheduler["last_job_id"] = job.job_id
        scheduler["consecutive_runs"] = 1
    state["updated_at"] = utc_text(completed_at)


def acquire_lock(lock_path: Path) -> None:
    if lock_path.exists():
        try:
            payload = json.loads(lock_path.read_text(encoding="ascii"))
            pid = int(payload.get("pid", 0))
            if pid > 0:
                os.kill(pid, 0)
                raise RuntimeError(f"priority loop already running (pid={pid})")
        except ProcessLookupError:
            pass
        except OSError:
            pass
        except (ValueError, json.JSONDecodeError):
            pass

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_payload = {"pid": os.getpid(), "started_at": utc_text()}
    lock_path.write_text(json.dumps(lock_payload, indent=2), encoding="ascii")


def release_lock(lock_path: Path) -> None:
    if lock_path.exists():
        try:
            payload = json.loads(lock_path.read_text(encoding="ascii"))
            if int(payload.get("pid", -1)) == os.getpid():
                lock_path.unlink(missing_ok=True)
        except Exception:
            lock_path.unlink(missing_ok=True)


def run_loop(
    queue: QueueConfig,
    *,
    state_path: Path,
    python_exe: str,
    status_backend: str,
    once: bool,
    max_jobs: int | None,
    max_minutes: float | None,
    dry_run: bool,
) -> None:
    state = read_state(state_path)
    state["queue_name"] = queue.name
    write_state(state_path, state)

    loop_started = time.monotonic()
    jobs_completed = 0

    while True:
        if max_minutes is not None and (time.monotonic() - loop_started) >= max_minutes * 60.0:
            print("time budget reached; exiting.")
            break
        if max_jobs is not None and jobs_completed >= max_jobs:
            print("job budget reached; exiting.")
            break

        now = utc_now()
        state = read_state(state_path)
        job, wait_seconds = choose_next_job(queue, state, now=now)
        if job is None:
            sleep_for = max(queue.idle_sleep_seconds, wait_seconds)
            print(json.dumps({"stage": "idle", "sleep_seconds": round(sleep_for, 2), "updated_at": utc_text(now)}, indent=2))
            time.sleep(sleep_for)
            continue

        run_id = build_run_id(queue.default_run_prefix, job.job_id, now=now)
        command = build_job_command(job, python_exe=python_exe, run_id=run_id, status_backend=status_backend)

        print(
            json.dumps(
                {
                    "stage": "dispatch",
                    "job_id": job.job_id,
                    "kind": job.kind,
                    "priority": job.priority,
                    "run_id": run_id,
                    "command": command,
                },
                indent=2,
            )
        )

        if dry_run:
            jobs_completed += 1
            if once:
                break
            time.sleep(queue.post_job_pause_seconds)
            continue

        update_state_started(state, job, run_id, now)
        write_state(state_path, state)
        result = subprocess.run(command, check=False)
        completed = utc_now()

        state = read_state(state_path)
        update_state_completed(state, job, run_id, now, completed, int(result.returncode))
        write_state(state_path, state)

        jobs_completed += 1
        if once:
            break
        time.sleep(queue.post_job_pause_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a priority-scored Colab job loop for Hex6.")
    parser.add_argument(
        "--queue",
        default="configs/colab_job_queue.toml",
        help="Path to TOML queue config.",
    )
    parser.add_argument(
        "--state",
        default="artifacts/colab_queue/state.json",
        help="Path to scheduler state file.",
    )
    parser.add_argument(
        "--python-exe",
        default="python",
        help="Python executable used to launch jobs.",
    )
    parser.add_argument(
        "--status-backend",
        default=None,
        help="Override queue default status backend.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one selected job and exit.",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        help="Maximum number of jobs to run before exit.",
    )
    parser.add_argument(
        "--max-minutes",
        type=float,
        default=None,
        help="Maximum loop runtime in minutes before exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Select and print job commands without launching them.",
    )
    args = parser.parse_args()

    queue = load_queue_config(args.queue)
    status_backend = args.status_backend or queue.default_status_backend
    state_path = Path(args.state)
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")

    acquire_lock(lock_path)
    try:
        run_loop(
            queue,
            state_path=state_path,
            python_exe=args.python_exe,
            status_backend=status_backend,
            once=args.once,
            max_jobs=args.max_jobs,
            max_minutes=args.max_minutes,
            dry_run=args.dry_run,
        )
    finally:
        release_lock(lock_path)


if __name__ == "__main__":
    main()
