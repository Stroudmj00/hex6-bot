"""Print a compact status snapshot for a Colab autopilot worker."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from typing import Any

from hex6.integration.autopilot import list_job_requests, load_autopilot_config


def main() -> None:
    args = build_parser().parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    if args.watch:
        poll = 0
        while args.max_polls <= 0 or poll < args.max_polls:
            poll += 1
            snapshot = build_snapshot(
                repo_root=repo_root,
                plan_path=args.plan,
                worker_state_path=args.worker_state,
                worker_log_path=args.worker_log,
                tail_lines=args.tail_lines,
            )
            print_snapshot(snapshot, json_output=args.json)
            if args.max_polls > 0 and poll >= args.max_polls:
                break
            time.sleep(args.interval)
        return

    snapshot = build_snapshot(
        repo_root=repo_root,
        plan_path=args.plan,
        worker_state_path=args.worker_state,
        worker_log_path=args.worker_log,
        tail_lines=args.tail_lines,
    )
    print_snapshot(snapshot, json_output=args.json)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect Colab autopilot requests, progress, results, and worker logs.")
    parser.add_argument("--repo-root", default=".", help="Repository root in the Colab runtime.")
    parser.add_argument("--plan", default="configs/colab_autopilot.toml", help="Autopilot plan path.")
    parser.add_argument("--worker-state", default="artifacts/colab_autopilot/worker_state.json")
    parser.add_argument("--worker-log", default="artifacts/colab_autopilot/worker.log")
    parser.add_argument("--tail-lines", type=int, default=80)
    parser.add_argument("--json", action="store_true", help="Print the raw snapshot as JSON.")
    parser.add_argument("--watch", action="store_true", help="Keep polling until interrupted or --max-polls is reached.")
    parser.add_argument("--interval", type=float, default=30.0, help="Seconds between watch polls.")
    parser.add_argument("--max-polls", type=int, default=0, help="Maximum watch polls; 0 means unbounded.")
    return parser


def build_snapshot(
    *,
    repo_root: Path,
    plan_path: str,
    worker_state_path: str,
    worker_log_path: str,
    tail_lines: int,
) -> dict[str, Any]:
    config = load_autopilot_config(repo_root / plan_path)
    requests = list_job_requests(config)
    worker_state = _read_json(repo_root / worker_state_path)
    worker_pid = _coerce_pid(worker_state.get("pid"))
    worker_state["running"] = worker_pid is not None and _pid_is_running(worker_pid)

    focus_request = _select_focus_request(requests)
    focus_output = _request_output_path(repo_root, focus_request)
    progress = _latest_json_file(focus_output.rglob("progress.json")) if focus_output else {}
    result = _latest_json_file(Path(config.result_dir).glob("*.json"))
    summary = _latest_summary_file(focus_output)

    return {
        "generated_at": utc_text(),
        "repo_root": str(repo_root),
        "plan": str((repo_root / plan_path).resolve()),
        "worker": worker_state,
        "focus_request": focus_request,
        "focus_output": str(focus_output) if focus_output else "",
        "requests": requests,
        "latest_progress": progress,
        "latest_result": result,
        "latest_cycle_summary": summary,
        "worker_log_tail": _tail(repo_root / worker_log_path, lines=tail_lines),
    }


def print_snapshot(snapshot: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(snapshot, indent=2))
        return

    print(f"generated_at: {snapshot['generated_at']}")
    print(f"repo_root: {snapshot['repo_root']}")

    worker = snapshot.get("worker", {})
    if worker:
        print(
            "worker: "
            f"pid={worker.get('pid', '')} "
            f"running={worker.get('running', False)} "
            f"started_at={worker.get('started_at', '')}"
        )
        if worker.get("log_path"):
            print(f"worker_log: {worker['log_path']}")
    else:
        print("worker: no worker_state.json found")

    focus = snapshot.get("focus_request", {})
    if focus:
        print(f"focus_request: {focus.get('status', '')} {focus.get('request_id', '')}")
    if snapshot.get("focus_output"):
        print(f"focus_output: {snapshot['focus_output']}")

    print("requests:")
    rows = snapshot.get("requests", [])
    if not rows:
        print("- none")
    for row in rows:
        print(
            "- "
            f"{row.get('status', '')} "
            f"{row.get('request_id', '')} "
            f"kind={row.get('kind', '')} "
            f"priority={row.get('priority', '')} "
            f"run_id={row.get('run_id', '')} "
            f"exit={row.get('exit_code', '')}"
        )

    _print_json_section("latest_progress", snapshot.get("latest_progress", {}))
    _print_json_section("latest_result", snapshot.get("latest_result", {}))
    _print_json_section("latest_cycle_summary", snapshot.get("latest_cycle_summary", {}))

    tail = snapshot.get("worker_log_tail", [])
    if tail:
        print("worker_log_tail:")
        for line in tail:
            print(line.rstrip())


def _print_json_section(title: str, payload: dict[str, Any]) -> None:
    if not payload:
        print(f"{title}: none")
        return
    print(f"{title}: {payload.get('path', '')}")
    content = payload.get("content", {})
    if isinstance(content, dict):
        print(json.dumps(content, indent=2)[:4000])
    else:
        print(str(content)[:4000])


def _latest_json_file(paths: Iterable[Path]) -> dict[str, Any]:
    candidates = [path for path in paths if path.is_file()]
    if not candidates:
        return {}
    path = max(candidates, key=lambda item: item.stat().st_mtime)
    return {
        "path": str(path),
        "modified_at": utc_text(datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)),
        "content": _read_json(path),
    }


def _latest_summary_file(output_path: Path | None) -> dict[str, Any]:
    if output_path is None:
        return {}
    candidates = [output_path / "cycle_summary.json", output_path / "summary.json", output_path / "ladder_summary.json"]
    return _latest_json_file(path for path in candidates if path.exists())


def _select_focus_request(requests: list[dict[str, Any]]) -> dict[str, Any]:
    for status in ("running", "completed", "failed", "pending"):
        candidates = [row for row in requests if row.get("status") == status]
        if candidates:
            return max(candidates, key=_request_timestamp)
    return {}


def _request_timestamp(row: dict[str, Any]) -> str:
    for key in ("completed_at", "claimed_at", "created_at"):
        value = str(row.get(key, "")).strip()
        if value:
            return value
    return ""


def _request_output_path(repo_root: Path, request: dict[str, Any]) -> Path | None:
    options = request.get("options")
    if not isinstance(options, dict):
        return None
    value = str(options.get("output_root") or options.get("output") or "").strip()
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = repo_root / path
    return path


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="ascii"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _tail(path: Path, *, lines: int) -> list[str]:
    if lines <= 0 or not path.exists():
        return []
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return [f"failed to read {path}: {exc}"]
    return content[-lines:]


def _coerce_pid(value: object) -> int | None:
    try:
        pid = int(value)
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def _pid_is_running(pid: int) -> bool:
    if os.name == "nt":
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def utc_text(moment: datetime | None = None) -> str:
    dt = moment or datetime.now(timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    main()
