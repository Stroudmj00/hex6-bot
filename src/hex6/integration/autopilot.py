"""File-backed Colab autopilot broker and research backlog helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
import tomllib
from typing import Any

from .run_priority_loop import JobSpec, build_job_command, build_run_id


@dataclass(frozen=True)
class AutopilotConfig:
    name: str
    request_dir: str
    result_dir: str
    state_path: str
    default_status_backend: str
    default_run_prefix: str
    poll_seconds: float
    research_backlog_path: str
    research_state_path: str
    research_note_dir: str
    source_path: str


@dataclass(frozen=True)
class JobRequest:
    request_id: str
    kind: str
    priority: int
    created_at: str
    notes: str = ""
    return_policy: str = "auto"
    options: dict[str, Any] = field(default_factory=dict)
    claimed_at: str = ""
    claimed_by: str = ""
    completed_at: str = ""
    run_id: str = ""
    status: str = "pending"
    exit_code: int | None = None
    error: str = ""


@dataclass(frozen=True)
class ResearchIdea:
    idea_id: str
    title: str
    priority: int
    summary: str
    deliverable: str = ""
    source_refs: tuple[str, ...] = ()
    notes: str = ""


def load_autopilot_config(path: str | Path) -> AutopilotConfig:
    config_path = Path(path).resolve()
    base_root = _config_base_root(config_path)
    with config_path.open("rb") as handle:
        data = tomllib.load(handle)
    table = data.get("autopilot", {})
    return AutopilotConfig(
        name=str(table.get("name", "hex6_colab_autopilot")),
        request_dir=str(_resolve_rooted_path(base_root, str(table.get("request_dir", "artifacts/colab_autopilot/requests")))),
        result_dir=str(_resolve_rooted_path(base_root, str(table.get("result_dir", "artifacts/colab_autopilot/results")))),
        state_path=str(_resolve_rooted_path(base_root, str(table.get("state_path", "artifacts/colab_autopilot/state.json")))),
        default_status_backend=str(table.get("default_status_backend", "github_branch")),
        default_run_prefix=str(table.get("default_run_prefix", "autocolab")),
        poll_seconds=max(float(table.get("poll_seconds", 30.0)), 1.0),
        research_backlog_path=str(
            _resolve_rooted_path(base_root, str(table.get("research_backlog_path", "configs/colab_research_backlog.toml")))
        ),
        research_state_path=str(
            _resolve_rooted_path(base_root, str(table.get("research_state_path", "artifacts/colab_autopilot/research_state.json")))
        ),
        research_note_dir=str(
            _resolve_rooted_path(base_root, str(table.get("research_note_dir", "artifacts/colab_autopilot/research_notes")))
        ),
        source_path=str(config_path),
    )


def submit_job_request(
    config: AutopilotConfig,
    *,
    request_id: str,
    kind: str,
    priority: int,
    notes: str = "",
    return_policy: str = "auto",
    options: dict[str, Any] | None = None,
) -> Path:
    ensure_autopilot_layout(config)
    request = JobRequest(
        request_id=request_id,
        kind=kind,
        priority=int(priority),
        created_at=utc_text(),
        notes=notes,
        return_policy=return_policy,
        options=dict(options or {}),
    )
    for status in ("pending", "running", "completed", "failed"):
        existing = _request_status_dir(config, status) / f"{request_id}.json"
        if existing.exists():
            raise ValueError(f"job request already exists: {request_id}")
    path = _request_status_dir(config, "pending") / f"{request.request_id}.json"
    _write_json(path, asdict(request))
    state = read_autopilot_state(config.state_path)
    _append_history(
        state,
        {
            "stage": "submitted",
            "request_id": request.request_id,
            "kind": request.kind,
            "priority": request.priority,
            "created_at": request.created_at,
        },
    )
    write_autopilot_state(config.state_path, state)
    return path


def list_job_requests(config: AutopilotConfig) -> list[dict[str, Any]]:
    ensure_autopilot_layout(config)
    rows: list[dict[str, Any]] = []
    for status in ("pending", "running", "completed", "failed"):
        for path in sorted(_request_status_dir(config, status).glob("*.json")):
            payload = _read_json(path)
            payload["status"] = status
            payload["path"] = str(path)
            rows.append(payload)
    rows.sort(key=_job_request_sort_key)
    return rows


def peek_next_job_request(config: AutopilotConfig) -> JobRequest | None:
    ensure_autopilot_layout(config)
    pending: list[JobRequest] = []
    for path in _request_status_dir(config, "pending").glob("*.json"):
        pending.append(_job_request_from_payload(_read_json(path)))
    if not pending:
        return None
    pending.sort(key=_job_request_sort_key)
    return pending[0]


def claim_next_job_request(config: AutopilotConfig, *, worker_id: str, run_id: str) -> JobRequest | None:
    candidate = peek_next_job_request(config)
    if candidate is None:
        return None
    source = _request_status_dir(config, "pending") / f"{candidate.request_id}.json"
    target = _request_status_dir(config, "running") / f"{candidate.request_id}.json"
    try:
        source.replace(target)
    except FileNotFoundError:
        return None

    payload = _read_json(target)
    payload.update(
        {
            "status": "running",
            "claimed_at": utc_text(),
            "claimed_by": worker_id,
            "run_id": run_id,
        }
    )
    _write_json(target, payload)

    state = read_autopilot_state(config.state_path)
    _append_history(
        state,
        {
            "stage": "claimed",
            "request_id": candidate.request_id,
            "kind": candidate.kind,
            "claimed_by": worker_id,
            "run_id": run_id,
            "claimed_at": payload["claimed_at"],
        },
    )
    workers = state.setdefault("workers", {})
    workers[worker_id] = {"last_claimed_at": payload["claimed_at"], "last_run_id": run_id}
    write_autopilot_state(config.state_path, state)
    return _job_request_from_payload(payload)


def complete_job_request(
    config: AutopilotConfig,
    *,
    request_id: str,
    success: bool,
    exit_code: int,
    result_payload: dict[str, Any],
    error: str = "",
) -> Path:
    ensure_autopilot_layout(config)
    source = _request_status_dir(config, "running") / f"{request_id}.json"
    if not source.exists():
        raise FileNotFoundError(f"running request not found: {request_id}")
    target_status = "completed" if success else "failed"
    target = _request_status_dir(config, target_status) / f"{request_id}.json"
    source.replace(target)
    payload = _read_json(target)
    payload.update(
        {
            "status": target_status,
            "completed_at": utc_text(),
            "exit_code": int(exit_code),
            "error": error,
        }
    )
    _write_json(target, payload)

    result_path = Path(config.result_dir) / f"{request_id}.json"
    result_document = {
        "request": payload,
        "result": result_payload,
        "generated_at": utc_text(),
    }
    _write_json(result_path, result_document)

    state = read_autopilot_state(config.state_path)
    _append_history(
        state,
        {
            "stage": target_status,
            "request_id": request_id,
            "exit_code": int(exit_code),
            "completed_at": payload["completed_at"],
            "result_path": str(result_path),
        },
    )
    write_autopilot_state(config.state_path, state)
    return result_path


def run_worker_loop(
    config: AutopilotConfig,
    *,
    repo_root: str | Path,
    python_exe: str,
    worker_id: str,
    status_backend: str | None = None,
    once: bool = False,
    max_jobs: int | None = None,
    dry_run: bool = False,
) -> None:
    jobs_completed = 0
    selected_status_backend = status_backend or config.default_status_backend
    resolved_repo_root = Path(repo_root).resolve()
    while True:
        if max_jobs is not None and jobs_completed >= max_jobs:
            print("job budget reached; exiting.")
            break

        if dry_run:
            request = peek_next_job_request(config)
            if request is None:
                print(json.dumps({"stage": "idle", "updated_at": utc_text()}, indent=2))
                break
            run_id = build_run_id(config.default_run_prefix, request.request_id)
            command = build_job_command(
                JobSpec(request.request_id, request.kind, request.priority, True, 0.0, dict(request.options)),
                python_exe=python_exe,
                run_id=run_id,
                status_backend=selected_status_backend,
            )
            print(
                json.dumps(
                    {
                        "stage": "dispatch_preview",
                        "request_id": request.request_id,
                        "kind": request.kind,
                        "priority": request.priority,
                        "run_id": run_id,
                        "command": command,
                    },
                    indent=2,
                )
            )
            break

        request = peek_next_job_request(config)
        if request is None:
            if once:
                print(json.dumps({"stage": "idle", "updated_at": utc_text()}, indent=2))
                break
            print(json.dumps({"stage": "idle", "sleep_seconds": config.poll_seconds, "updated_at": utc_text()}, indent=2))
            time.sleep(config.poll_seconds)
            continue

        run_id = build_run_id(config.default_run_prefix, request.request_id)
        request = claim_next_job_request(config, worker_id=worker_id, run_id=run_id)
        if request is None:
            continue
        running_path = _request_status_dir(config, "running") / f"{request.request_id}.json"
        payload = _read_json(running_path)
        payload["run_id"] = run_id
        _write_json(running_path, payload)

        command = build_job_command(
            JobSpec(request.request_id, request.kind, request.priority, True, 0.0, dict(request.options)),
            python_exe=python_exe,
            run_id=run_id,
            status_backend=selected_status_backend,
        )
        print(
            json.dumps(
                {
                    "stage": "dispatch",
                    "request_id": request.request_id,
                    "kind": request.kind,
                    "priority": request.priority,
                    "run_id": run_id,
                    "command": command,
                },
                indent=2,
            )
        )
        completed = subprocess.run(command, cwd=resolved_repo_root, check=False)
        result_payload = build_request_result(config, request, repo_root=resolved_repo_root)
        complete_job_request(
            config,
            request_id=request.request_id,
            success=int(completed.returncode) == 0,
            exit_code=int(completed.returncode),
            result_payload=result_payload,
            error="" if int(completed.returncode) == 0 else f"job exited with code {int(completed.returncode)}",
        )
        jobs_completed += 1
        if once:
            break


def build_request_result(
    config: AutopilotConfig,
    request: JobRequest,
    *,
    repo_root: str | Path,
) -> dict[str, Any]:
    del config
    root = Path(repo_root).resolve()
    payload: dict[str, Any] = {
        "kind": request.kind,
        "return_policy": request.return_policy,
        "notes": request.notes,
    }
    options = request.options

    if request.kind == "bootstrap":
        output = _resolve_runtime_path(root, str(options.get("output", "artifacts/bootstrap_colab")))
        checkpoint = output / "bootstrap_model.pt"
        metrics = output / "metrics.json"
        raw_output = Path(str(options.get("output", "artifacts/bootstrap_colab")))
        payload.update(
            _artifact_payload(
                checkpoint_path=checkpoint,
                checkpoint_value=str(raw_output / "bootstrap_model.pt"),
                summary_path=metrics,
                config_path=options.get("config"),
            )
        )
    elif request.kind == "cycle":
        output_root = _resolve_runtime_path(root, str(options.get("output_root", "artifacts/bootstrap_colab_hour")))
        summary = output_root / "cycle_summary.json"
        payload["summary_path"] = str(summary)
        payload["resolved_summary_path"] = str(summary.resolve())
        if summary.exists():
            cycle_summary = _read_json(summary)
            latest_checkpoint = str(cycle_summary.get("latest_checkpoint", "")).strip()
            best_checkpoint = str(cycle_summary.get("best_checkpoint", "")).strip()
            if latest_checkpoint:
                payload["latest_checkpoint"] = latest_checkpoint
                payload["resolved_latest_checkpoint"] = str(_resolve_runtime_path(root, latest_checkpoint))
            if best_checkpoint:
                payload["best_checkpoint"] = best_checkpoint
                payload["resolved_best_checkpoint"] = str(_resolve_runtime_path(root, best_checkpoint))
            checkpoint_value = best_checkpoint or latest_checkpoint
            if checkpoint_value:
                payload.update(
                    _artifact_payload(
                        checkpoint_path=_resolve_runtime_path(root, checkpoint_value),
                        checkpoint_value=checkpoint_value,
                        summary_path=summary,
                        config_path=options.get("config"),
                    )
                )
    elif request.kind == "ladder":
        output = _resolve_runtime_path(root, str(options.get("output", "artifacts/colab_ladder")))
        summary = output / "ladder_summary.json"
        payload["summary_path"] = str(summary)
        payload["resolved_summary_path"] = str(summary.resolve())
    elif request.kind == "search_matrix":
        output = _resolve_runtime_path(root, str(options.get("output", "artifacts/search_matrix_colab")))
        summary = output / "summary.json"
        payload["summary_path"] = str(summary)
        payload["resolved_summary_path"] = str(summary.resolve())
    elif request.kind == "runtime_benchmark":
        output = _resolve_runtime_path(root, str(options.get("output", "artifacts/runtime_parallelism_colab")))
        summary = output / "summary.json"
        payload["summary_path"] = str(summary)
        payload["resolved_summary_path"] = str(summary.resolve())
    elif request.kind == "tournament":
        output = _resolve_runtime_path(root, str(options.get("output", "artifacts/tournament_colab")))
        summary = output / "summary.json"
        payload["summary_path"] = str(summary)
        payload["resolved_summary_path"] = str(summary.resolve())
    return payload


def load_research_backlog(config: AutopilotConfig) -> tuple[ResearchIdea, ...]:
    backlog_path = Path(config.research_backlog_path)
    with backlog_path.open("rb") as handle:
        data = tomllib.load(handle)
    rows = data.get("ideas", [])
    return tuple(
        ResearchIdea(
            idea_id=str(row["idea_id"]).strip(),
            title=str(row["title"]).strip(),
            priority=int(row.get("priority", 0)),
            summary=str(row.get("summary", "")).strip(),
            deliverable=str(row.get("deliverable", "")).strip(),
            source_refs=tuple(str(value).strip() for value in row.get("source_refs", [])),
            notes=str(row.get("notes", "")).strip(),
        )
        for row in rows
    )


def claim_next_research_idea(config: AutopilotConfig, *, researcher_id: str) -> ResearchIdea | None:
    backlog = load_research_backlog(config)
    state = read_research_state(config.research_state_path)
    completed = set(str(value) for value in state.get("completed", []))
    active = {str(key): value for key, value in state.get("active", {}).items()}
    pending = [
        idea
        for idea in backlog
        if idea.idea_id not in completed and idea.idea_id not in active
    ]
    if not pending:
        return None
    pending = sorted(pending, key=lambda item: (-item.priority, item.idea_id))
    idea = pending[0]
    active[idea.idea_id] = {"claimed_by": researcher_id, "claimed_at": utc_text()}
    state["active"] = active
    history = state.setdefault("history", [])
    history.append(
        {
            "stage": "claimed",
            "idea_id": idea.idea_id,
            "claimed_by": researcher_id,
            "claimed_at": active[idea.idea_id]["claimed_at"],
        }
    )
    write_research_state(config.research_state_path, state)
    return idea


def complete_research_idea(config: AutopilotConfig, *, idea_id: str, note_path: str = "") -> None:
    state = read_research_state(config.research_state_path)
    active = {str(key): value for key, value in state.get("active", {}).items()}
    active.pop(idea_id, None)
    state["active"] = active
    completed = list(dict.fromkeys([*(str(value) for value in state.get("completed", [])), idea_id]))
    state["completed"] = completed
    history = state.setdefault("history", [])
    history.append(
        {
            "stage": "completed",
            "idea_id": idea_id,
            "completed_at": utc_text(),
            "note_path": note_path,
        }
    )
    write_research_state(config.research_state_path, state)


def build_research_prompt(idea: ResearchIdea) -> str:
    refs = "\n".join(f"- {value}" for value in idea.source_refs)
    return "\n".join(
        [
            "You are an AI research operator working inside the Hex6 repository.",
            "Your job is to generate one concrete engine-improvement proposal while Colab is busy on compute jobs.",
            "",
            f"Idea ID: {idea.idea_id}",
            f"Title: {idea.title}",
            f"Priority: {idea.priority}",
            "",
            "Task:",
            idea.summary,
            "",
            "Deliverable:",
            idea.deliverable or "Produce a concise repo-grounded note with rationale, code targets, config impacts, and a validation plan.",
            "",
            "Required source files to read first:",
            refs or "- README.md\n- AGENTS.md\n- docs/literature-roadmap.md",
            "",
            "Constraints:",
            "- Keep behavior config-first.",
            "- Do not start long training runs.",
            "- Prefer small local tests or smokes only.",
            "- If you propose new config knobs, update profiles and tests in the same change.",
            "",
            "Output format:",
            "1. Problem",
            "2. Proposed change",
            "3. Code touch points",
            "4. Validation plan",
            "5. Whether this should become a new Colab job request",
        ]
    )


def read_autopilot_state(path: str | Path) -> dict[str, Any]:
    state_path = Path(path)
    if not state_path.exists():
        return {"history": [], "workers": {}}
    return _read_json(state_path)


def write_autopilot_state(path: str | Path, payload: dict[str, Any]) -> None:
    _write_json(Path(path), payload)


def read_research_state(path: str | Path) -> dict[str, Any]:
    state_path = Path(path)
    if not state_path.exists():
        return {"active": {}, "completed": [], "history": []}
    return _read_json(state_path)


def write_research_state(path: str | Path, payload: dict[str, Any]) -> None:
    _write_json(Path(path), payload)


def ensure_autopilot_layout(config: AutopilotConfig) -> None:
    request_root = Path(config.request_dir)
    for status in ("pending", "running", "completed", "failed"):
        (request_root / status).mkdir(parents=True, exist_ok=True)
    Path(config.result_dir).mkdir(parents=True, exist_ok=True)
    Path(config.state_path).parent.mkdir(parents=True, exist_ok=True)
    Path(config.research_state_path).parent.mkdir(parents=True, exist_ok=True)
    Path(config.research_note_dir).mkdir(parents=True, exist_ok=True)


def utc_text(moment: datetime | None = None) -> str:
    dt = moment or datetime.now(timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def generate_request_id(prefix: str, *, now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    return f"{prefix}-{moment.strftime('%Y%m%d-%H%M%S')}"


def _request_status_dir(config: AutopilotConfig, status: str) -> Path:
    return Path(config.request_dir) / status


def _artifact_payload(
    *,
    checkpoint_path: Path,
    checkpoint_value: str = "",
    summary_path: Path,
    config_path: Any,
) -> dict[str, Any]:
    raw_checkpoint = checkpoint_value or str(checkpoint_path)
    payload: dict[str, Any] = {
        "checkpoint_path": raw_checkpoint,
        "resolved_checkpoint_path": str(checkpoint_path.resolve()),
        "summary_path": str(summary_path),
        "resolved_summary_path": str(summary_path.resolve()),
    }
    if config_path:
        payload["config_path"] = str(config_path)
        payload["suggested_ladder_submission"] = {
            "kind": "checkpoint",
            "config_path": str(config_path),
            "checkpoint_path": raw_checkpoint,
            "notes": "Autopilot-returned training candidate.",
        }
    return payload


def _job_request_from_payload(payload: dict[str, Any]) -> JobRequest:
    return JobRequest(
        request_id=str(payload.get("request_id", "")).strip(),
        kind=str(payload.get("kind", "")).strip(),
        priority=int(payload.get("priority", 0)),
        created_at=str(payload.get("created_at", "")).strip(),
        notes=str(payload.get("notes", "")).strip(),
        return_policy=str(payload.get("return_policy", "auto")).strip() or "auto",
        options=dict(payload.get("options", {})),
        claimed_at=str(payload.get("claimed_at", "")).strip(),
        claimed_by=str(payload.get("claimed_by", "")).strip(),
        completed_at=str(payload.get("completed_at", "")).strip(),
        run_id=str(payload.get("run_id", "")).strip(),
        status=str(payload.get("status", "pending")).strip() or "pending",
        exit_code=(None if payload.get("exit_code") is None else int(payload["exit_code"])),
        error=str(payload.get("error", "")).strip(),
    )


def _job_request_sort_key(item: JobRequest | dict[str, Any]) -> tuple[int, str, str]:
    if isinstance(item, dict):
        status_order = {"pending": 0, "running": 1, "completed": 2, "failed": 3}
        return (
            status_order.get(str(item.get("status", "pending")), 9),
            -int(item.get("priority", 0)),
            str(item.get("created_at", "")),
        )
    return (-item.priority, item.created_at, item.request_id)


def _append_history(state: dict[str, Any], entry: dict[str, Any]) -> None:
    history = state.setdefault("history", [])
    history.append(entry)
    if len(history) > 500:
        del history[: len(history) - 500]
    state["updated_at"] = utc_text()


def _resolve_path(reference_path: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = (reference_path.parent / path).resolve()
    return path


def _resolve_rooted_path(base_root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = (base_root / path).resolve()
    return path


def _config_base_root(config_path: Path) -> Path:
    if config_path.parent.name.lower() == "configs":
        return config_path.parent.parent.resolve()
    return config_path.parent.resolve()


def _resolve_runtime_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    return path


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="ascii"))


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="ascii")
