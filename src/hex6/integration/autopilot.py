"""File-backed Colab autopilot broker and research backlog helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
import tomllib
from typing import Any, Iterable
import zipfile

from .run_priority_loop import JobSpec, build_job_command, build_run_id


COLAB_DRIVE_PREFIX = "/content/drive"
STORAGE_PREFLIGHT_EXIT_CODE = 78


@dataclass(frozen=True)
class AutopilotConfig:
    name: str
    request_dir: str
    result_dir: str
    state_path: str
    default_status_backend: str
    default_run_prefix: str
    poll_seconds: float
    default_job_timeout_minutes: float
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
        default_job_timeout_minutes=max(float(table.get("default_job_timeout_minutes", 0.0)), 0.0),
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


def get_job_request(config: AutopilotConfig, request_id: str) -> JobRequest | None:
    ensure_autopilot_layout(config)
    for status in ("pending", "running", "completed", "failed"):
        path = _request_status_dir(config, status) / f"{request_id}.json"
        if path.exists():
            payload = _read_json(path)
            payload["status"] = status
            return _job_request_from_payload(payload)
    return None


def validate_job_storage(
    config: AutopilotConfig,
    request: JobRequest,
    *,
    repo_root: str | Path,
    write_probe: bool = True,
) -> dict[str, Any]:
    """Validate that a request's output directory can preserve returned evidence."""
    ensure_autopilot_layout(config)
    root = Path(repo_root).resolve()
    checks = [
        _check_storage_target(label, raw_path, path, write_probe=write_probe)
        for label, raw_path, path in _job_output_storage_targets(request, root)
    ]
    errors = [str(check["error"]) for check in checks if not check.get("ok")]
    return {
        "ok": not errors,
        "request_id": request.request_id,
        "kind": request.kind,
        "repo_root": str(root),
        "write_probe": write_probe,
        "checks": checks,
        "errors": errors,
    }


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


def export_result_bundle(
    config: AutopilotConfig,
    result_path: str | Path,
    *,
    repo_root: str | Path,
    output_path: str | Path | None = None,
    include_checkpoint: bool = True,
    include_worker_log: bool = True,
) -> dict[str, Any]:
    """Bundle a completed result and key evidence into a portable zip file."""
    ensure_autopilot_layout(config)
    root = Path(repo_root).resolve()
    result_file = Path(result_path).resolve()
    document = _read_json(result_file)
    request = _mapping(document.get("request"))
    result = _mapping(document.get("result"))
    request_id = str(request.get("request_id") or result_file.stem).strip() or result_file.stem
    safe_request_id = _safe_identifier(request_id)
    bundle_path = (
        Path(output_path).resolve()
        if output_path is not None
        else Path(config.result_dir).resolve().parent / "exports" / f"{safe_request_id}.zip"
    )

    candidates: list[Path] = [result_file]
    missing: list[str] = []
    _append_existing_request_file(config, request_id, candidates)
    _append_result_path(result, "resolved_summary_path", root, candidates, missing)
    _append_result_path(result, "summary_path", root, candidates, missing)
    if include_checkpoint:
        for key in ("resolved_checkpoint_path", "checkpoint_path", "resolved_best_checkpoint", "best_checkpoint", "resolved_latest_checkpoint", "latest_checkpoint"):
            _append_result_path(result, key, root, candidates, missing)
    for key in ("config_path",):
        _append_result_path(result, key, root, candidates, missing)
    suggestion = _mapping(result.get("suggested_ladder_submission"))
    for key in ("config_path",):
        _append_result_path(suggestion, key, root, candidates, missing)
    if include_worker_log:
        worker_log = root / "artifacts" / "colab_autopilot" / "worker.log"
        if worker_log.exists():
            candidates.append(worker_log)

    # Cycle summaries point to the cycle directory; include small nearby evidence files.
    for path in tuple(candidates):
        if path.name == "cycle_summary.json":
            _append_cycle_evidence(path, root, candidates)

    existing_files = _dedupe_paths(path for path in candidates if path.exists() and path.is_file())
    missing_files = sorted(set(missing))
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    included: list[str] = []
    used_names: set[str] = set()
    manifest = {
        "request_id": request_id,
        "generated_at": utc_text(),
        "result_path": _repo_relative_or_absolute(root, result_file),
        "repo_root": str(root),
        "included_files": [],
        "missing_files": missing_files,
    }
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in existing_files:
            arcname = _archive_name(root, file_path, used_names)
            archive.write(file_path, arcname)
            included.append(arcname)
        manifest["included_files"] = included
        archive.writestr("bundle_manifest.json", json.dumps(manifest, indent=2))

    return {
        "request_id": request_id,
        "bundle_path": str(bundle_path),
        "bundle_size_bytes": bundle_path.stat().st_size,
        "included_files": included,
        "missing_files": missing_files,
    }


def judge_request_result(
    config: AutopilotConfig,
    result_path: str | Path,
    *,
    manifest_path: str | Path | None = None,
    submit_ladder: bool = False,
    ladder_request_id: str | None = None,
    ladder_config: str = "configs/colab_ladder.toml",
    ladder_priority: int = 95,
    ladder_output: str | Path | None = None,
    max_submissions: int = 1,
) -> dict[str, Any]:
    """Classify a returned autopilot result and optionally enqueue a ladder gate."""
    ensure_autopilot_layout(config)
    result_file = Path(result_path).resolve()
    document = _read_json(result_file)
    request = _mapping(document.get("request"))
    result = _mapping(document.get("result"))
    request_id = str(request.get("request_id") or result_file.stem).strip() or result_file.stem
    kind = str(request.get("kind") or result.get("kind", "")).strip()
    repo_root = _config_base_root(Path(config.source_path).resolve())

    judgement: dict[str, Any] = {
        "request_id": request_id,
        "kind": kind,
        "result_path": str(result_file),
        "decision": "archive",
        "reasons": [],
    }
    reasons = judgement["reasons"]
    if not isinstance(reasons, list):
        raise TypeError("judgement reasons must be a list")

    exit_code = request.get("exit_code")
    status = str(request.get("status", "")).strip()
    if status and status != "completed":
        reasons.append(f"request_status_{status}")
    if exit_code not in (None, 0):
        reasons.append(f"nonzero_exit_code_{exit_code}")
    if reasons:
        return judgement

    if kind == "ladder":
        return _judge_ladder_result(judgement, result)

    if kind not in {"bootstrap", "cycle"}:
        reasons.append("no_checkpoint_gate_for_kind")
        return judgement

    checkpoint_value = _result_checkpoint_value(result)
    if not checkpoint_value:
        reasons.append("no_returned_checkpoint")
        return judgement

    checkpoint_path = _resolve_runtime_path(repo_root, checkpoint_value)
    judgement["checkpoint_path"] = checkpoint_value
    judgement["resolved_checkpoint_path"] = str(checkpoint_path)
    judgement["checkpoint_exists"] = checkpoint_path.exists()
    if not checkpoint_path.exists():
        judgement["decision"] = "follow_up"
        reasons.append("checkpoint_path_missing")
        return judgement

    candidate_config = _result_config_path(result)
    candidate_config_path = _resolve_runtime_path(repo_root, candidate_config) if candidate_config else None
    if candidate_config_path is not None and not candidate_config_path.exists():
        judgement["decision"] = "follow_up"
        judgement["config_path"] = candidate_config
        judgement["resolved_config_path"] = str(candidate_config_path)
        reasons.append("config_path_missing")
        return judgement

    safe_request_id = _safe_identifier(request_id)
    manifest_file = (
        Path(manifest_path).resolve()
        if manifest_path is not None
        else Path(config.result_dir).resolve().parent / "ladder_manifests" / f"{safe_request_id}.toml"
    )
    _write_ladder_manifest(
        manifest_file,
        repo_root=repo_root,
        request_id=request_id,
        submission_id=f"autopilot_{safe_request_id}",
        checkpoint_path=checkpoint_path,
        candidate_config_path=candidate_config_path,
    )
    manifest_for_job = _repo_relative_text(repo_root, manifest_file)
    judgement["decision"] = "submit_ladder" if submit_ladder else "ladder_manifest"
    judgement["ladder_manifest_path"] = str(manifest_file)
    judgement["ladder_manifest"] = manifest_for_job
    reasons.append("checkpoint_requires_ladder_gate")

    if submit_ladder:
        ladder_id = ladder_request_id or generate_request_id("ladder")
        output_value = (
            str(ladder_output)
            if ladder_output is not None
            else f"artifacts/colab_ladder/autopilot/{safe_request_id}"
        )
        options = {
            "config": ladder_config,
            "manifest": manifest_for_job,
            "output": output_value,
            "state": str(Path(output_value) / "state.json"),
            "ledger": str(Path(output_value) / "strength_ledger.jsonl"),
            "max_submissions": int(max_submissions),
            "resume": False,
        }
        request_path = submit_job_request(
            config,
            request_id=ladder_id,
            kind="ladder",
            priority=ladder_priority,
            notes=f"Ladder gate for autopilot result {request_id}.",
            options=options,
        )
        judgement["ladder_request_id"] = ladder_id
        judgement["ladder_request_path"] = str(request_path)
        judgement["ladder_request_options"] = options

    return judgement


def promote_champion_from_ladder(
    summary_path: str | Path,
    *,
    production_checkpoint_path: str | Path = "models/production/hex6_champion.pt",
    metadata_path: str | Path = "models/production/hex6_champion.metadata.json",
    apply: bool = False,
) -> dict[str, Any]:
    """Promote the ladder champion into the production checkpoint slot when evidence proves it."""
    summary_file = Path(summary_path).resolve()
    summary = _read_json(summary_file)
    promoted_ids = [str(value) for value in summary.get("promoted_submission_ids", [])]
    champion = _mapping(summary.get("champion"))
    champion_id = str(champion.get("submission_id", "")).strip()
    decision: dict[str, Any] = {
        "summary_path": str(summary_file),
        "decision": "no_promotion",
        "promoted_submission_ids": promoted_ids,
        "champion_submission_id": champion_id,
        "applied": False,
    }
    if not promoted_ids:
        decision["reason"] = "ladder_summary_has_no_promotions"
        return decision
    if champion_id not in promoted_ids:
        decision["reason"] = "current_ladder_champion_was_not_promoted"
        return decision

    raw_checkpoint = str(champion.get("checkpoint_path", "")).strip()
    if not raw_checkpoint:
        decision["decision"] = "invalid"
        decision["reason"] = "promoted_champion_missing_checkpoint_path"
        return decision
    manifest_path = Path(str(summary.get("manifest_path", ""))).resolve()
    if not str(summary.get("manifest_path", "")).strip():
        decision["decision"] = "invalid"
        decision["reason"] = "ladder_summary_missing_manifest_path"
        return decision
    checkpoint_path = _resolve_runtime_path(manifest_path.parent, raw_checkpoint)
    decision["source_checkpoint"] = str(checkpoint_path)
    decision["checkpoint_exists"] = checkpoint_path.exists()
    if not checkpoint_path.exists():
        decision["decision"] = "invalid"
        decision["reason"] = "promoted_checkpoint_missing"
        return decision

    production_checkpoint = Path(production_checkpoint_path).resolve()
    metadata_file = Path(metadata_path).resolve()
    metadata_payload = {
        "source_checkpoint": _repo_relative_or_absolute(Path.cwd().resolve(), checkpoint_path),
        "source_ladder_summary": _repo_relative_or_absolute(Path.cwd().resolve(), summary_file),
        "source_ladder_manifest": _repo_relative_or_absolute(Path.cwd().resolve(), manifest_path),
        "promoted_submission_id": champion_id,
        "promoted_submission_name": str(champion.get("name", "")).strip(),
        "selection_basis": "ladder_promoted_candidate",
        "notes": "Bundled production checkpoint promoted from a Hex6 ladder result.",
        "previous_metadata": _read_json(metadata_file) if metadata_file.exists() else {},
        "generated_at": utc_text(),
    }
    decision.update(
        {
            "decision": "promote_champion",
            "production_checkpoint_path": str(production_checkpoint),
            "metadata_path": str(metadata_file),
            "metadata": metadata_payload,
        }
    )
    if not apply:
        decision["reason"] = "dry_run"
        return decision

    production_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    metadata_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(checkpoint_path, production_checkpoint)
    _write_json(metadata_file, metadata_payload)
    decision["applied"] = True
    decision["reason"] = "applied"
    return decision


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
    job_timeout_minutes: float | None = None,
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
            timeout_minutes = _job_timeout_minutes(config, request, job_timeout_minutes)
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
                        "timeout_minutes": timeout_minutes,
                        "storage_preflight": validate_job_storage(
                            config,
                            request,
                            repo_root=resolved_repo_root,
                            write_probe=False,
                        ),
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

        timeout_minutes = _job_timeout_minutes(config, request, job_timeout_minutes)
        storage_preflight = validate_job_storage(config, request, repo_root=resolved_repo_root)
        if not storage_preflight["ok"]:
            error = _storage_preflight_error(storage_preflight)
            print(
                json.dumps(
                    {
                        "stage": "storage_preflight_failed",
                        "request_id": request.request_id,
                        "run_id": run_id,
                        "error": error,
                        "storage_preflight": storage_preflight,
                    },
                    indent=2,
                )
            )
            result_payload = build_request_result(config, request, repo_root=resolved_repo_root)
            result_payload["storage_preflight"] = storage_preflight
            result_path = complete_job_request(
                config,
                request_id=request.request_id,
                success=False,
                exit_code=STORAGE_PREFLIGHT_EXIT_CODE,
                result_payload=result_payload,
                error=error,
            )
            _emit_result_bundle(config, result_path, repo_root=resolved_repo_root, request_id=request.request_id)
            jobs_completed += 1
            if once:
                break
            continue

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
                    "timeout_minutes": timeout_minutes,
                },
                indent=2,
            )
        )
        timed_out = False
        error = ""
        try:
            completed = subprocess.run(
                command,
                cwd=resolved_repo_root,
                check=False,
                timeout=(timeout_minutes * 60.0 if timeout_minutes > 0 else None),
            )
            exit_code = int(completed.returncode)
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = 124
            error = f"job timed out after {timeout_minutes:g} minutes"
            print(
                json.dumps(
                    {
                        "stage": "job_timeout",
                        "request_id": request.request_id,
                        "run_id": run_id,
                        "timeout_minutes": timeout_minutes,
                        "command": exc.cmd,
                    },
                    indent=2,
                )
            )
        result_payload = build_request_result(config, request, repo_root=resolved_repo_root)
        if timed_out:
            result_payload["timed_out"] = True
            result_payload["timeout_minutes"] = timeout_minutes
        result_payload["storage_preflight"] = storage_preflight
        result_path = complete_job_request(
            config,
            request_id=request.request_id,
            success=exit_code == 0,
            exit_code=exit_code,
            result_payload=result_payload,
            error=error if error else ("" if exit_code == 0 else f"job exited with code {exit_code}"),
        )
        _emit_result_bundle(config, result_path, repo_root=resolved_repo_root, request_id=request.request_id)
        jobs_completed += 1
        if once:
            break


def _emit_result_bundle(
    config: AutopilotConfig,
    result_path: str | Path,
    *,
    repo_root: str | Path,
    request_id: str,
) -> None:
    try:
        bundle = export_result_bundle(config, result_path, repo_root=repo_root)
        print(json.dumps({"stage": "artifact_bundle", **bundle}, indent=2))
    except Exception as exc:  # pragma: no cover - best effort durability path
        print(
            json.dumps(
                {
                    "stage": "artifact_bundle_failed",
                    "request_id": request_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                indent=2,
            )
        )


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


def _job_timeout_minutes(config: AutopilotConfig, request: JobRequest, override: float | None) -> float:
    if override is not None:
        return max(float(override), 0.0)
    raw_request_timeout = request.options.get("timeout_minutes")
    if raw_request_timeout is not None:
        return max(float(raw_request_timeout), 0.0)
    return config.default_job_timeout_minutes


def _job_output_storage_targets(request: JobRequest, repo_root: Path) -> list[tuple[str, str, Path]]:
    options = request.options
    if request.kind == "bootstrap":
        raw_path = str(options.get("output", "artifacts/bootstrap_colab"))
        return [("job_output", raw_path, _resolve_runtime_path(repo_root, raw_path))]
    if request.kind == "cycle":
        raw_path = str(options.get("output_root", "artifacts/bootstrap_colab_hour"))
        return [("job_output_root", raw_path, _resolve_runtime_path(repo_root, raw_path))]
    if request.kind == "ladder":
        raw_path = str(options.get("output", "artifacts/colab_ladder"))
        return [("job_output", raw_path, _resolve_runtime_path(repo_root, raw_path))]
    if request.kind == "search_matrix":
        raw_path = str(options.get("output", "artifacts/search_matrix_colab"))
        return [("job_output", raw_path, _resolve_runtime_path(repo_root, raw_path))]
    if request.kind == "runtime_benchmark":
        raw_path = str(options.get("output", "artifacts/runtime_parallelism_colab"))
        return [("job_output", raw_path, _resolve_runtime_path(repo_root, raw_path))]
    if request.kind == "tournament":
        raw_path = str(options.get("output", "artifacts/tournament_colab"))
        return [("job_output", raw_path, _resolve_runtime_path(repo_root, raw_path))]
    return []


def _check_storage_target(label: str, raw_path: str, path: Path, *, write_probe: bool) -> dict[str, Any]:
    check: dict[str, Any] = {
        "label": label,
        "raw_path": raw_path,
        "resolved_path": str(path),
        "ok": True,
    }
    drive_error = _colab_drive_mount_error(raw_path)
    if drive_error:
        check.update({"ok": False, "error": drive_error})
        return check
    if not write_probe:
        check["exists"] = path.exists()
        return check
    try:
        path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir():
            check.update({"ok": False, "error": f"storage target is not a directory: {path}"})
            return check
        probe = path / ".hex6_autopilot_write_probe"
        probe.write_text("ok\n", encoding="ascii")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        check.update(
            {
                "ok": False,
                "error": f"storage target is not writable: {path} ({type(exc).__name__}: {exc})",
            }
        )
    return check


def _colab_drive_mount_error(raw_path: str) -> str:
    if not _is_colab_drive_path(raw_path):
        return ""
    drive_root = Path(COLAB_DRIVE_PREFIX)
    my_drive = drive_root / "MyDrive"
    if not drive_root.exists():
        return f"Colab Drive output requested but {COLAB_DRIVE_PREFIX} is not mounted"
    if not my_drive.exists():
        return f"Colab Drive output requested but {my_drive} is missing"
    try:
        is_mount = drive_root.is_mount()
    except (OSError, NotImplementedError):
        is_mount = False
    if not is_mount:
        return f"Colab Drive output requested but {COLAB_DRIVE_PREFIX} is not a mounted filesystem"
    return ""


def _is_colab_drive_path(raw_path: str) -> bool:
    normalized = raw_path.replace("\\", "/")
    return normalized == COLAB_DRIVE_PREFIX or normalized.startswith(f"{COLAB_DRIVE_PREFIX}/")


def _storage_preflight_error(report: dict[str, Any]) -> str:
    errors = [str(value) for value in report.get("errors", []) if str(value).strip()]
    if errors:
        return "storage preflight failed: " + "; ".join(errors)
    return "storage preflight failed"


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


def _append_existing_request_file(config: AutopilotConfig, request_id: str, candidates: list[Path]) -> None:
    for status in ("pending", "running", "completed", "failed"):
        path = _request_status_dir(config, status) / f"{request_id}.json"
        if path.exists():
            candidates.append(path.resolve())


def _append_result_path(
    payload: dict[str, Any],
    key: str,
    repo_root: Path,
    candidates: list[Path],
    missing: list[str],
) -> None:
    raw_value = str(payload.get(key, "")).strip()
    if not raw_value:
        return
    path = _resolve_runtime_path(repo_root, raw_value)
    if path.exists():
        candidates.append(path)
    else:
        missing.append(raw_value)


def _append_cycle_evidence(summary_path: Path, repo_root: Path, candidates: list[Path]) -> None:
    try:
        summary = _read_json(summary_path)
    except Exception:
        return
    for key in ("latest_checkpoint", "best_checkpoint"):
        raw_value = str(summary.get(key, "")).strip()
        if raw_value:
            path = _resolve_runtime_path(repo_root, raw_value)
            if path.exists():
                candidates.append(path)
    for cycle in summary.get("cycles", []):
        if not isinstance(cycle, dict):
            continue
        metrics = _mapping(cycle.get("metrics"))
        raw_checkpoint = str(metrics.get("checkpoint", "")).strip()
        if raw_checkpoint:
            checkpoint_path = _resolve_runtime_path(repo_root, raw_checkpoint)
            if checkpoint_path.exists():
                candidates.append(checkpoint_path)
            _append_nearby_cycle_files(checkpoint_path.parent, candidates)


def _append_nearby_cycle_files(cycle_dir: Path, candidates: list[Path]) -> None:
    if not cycle_dir.exists():
        return
    for relative in (
        "metrics.json",
        "arena.json",
        "post_train_tournament/summary.json",
        "promotion_match/summary.json",
        "human_exploit_probe/summary.json",
    ):
        path = cycle_dir / relative
        if path.exists():
            candidates.append(path)


def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path).resolve()
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _archive_name(repo_root: Path, file_path: Path, used_names: set[str]) -> str:
    try:
        arcname = file_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        arcname = f"external/{_safe_identifier(file_path.parent.name)}_{file_path.name}"
    candidate = arcname
    suffix = 2
    while candidate in used_names:
        path = Path(arcname)
        candidate = f"{path.with_suffix('').as_posix()}_{suffix}{path.suffix}"
        suffix += 1
    used_names.add(candidate)
    return candidate


def _judge_ladder_result(judgement: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    reasons = judgement["reasons"]
    if not isinstance(reasons, list):
        raise TypeError("judgement reasons must be a list")
    raw_summary_path = str(result.get("resolved_summary_path") or result.get("summary_path") or "").strip()
    if not raw_summary_path:
        judgement["summary_path"] = ""
        judgement["decision"] = "follow_up"
        reasons.append("ladder_summary_missing")
        return judgement
    summary_path = Path(raw_summary_path).resolve()
    judgement["summary_path"] = str(summary_path)
    if not summary_path.exists():
        judgement["decision"] = "follow_up"
        reasons.append("ladder_summary_missing")
        return judgement
    summary = _read_json(summary_path)
    promoted = list(summary.get("promoted_submission_ids", []))
    judgement["promoted_submission_ids"] = promoted
    judgement["processed_submission_ids"] = list(summary.get("processed_submission_ids", []))
    if promoted:
        judgement["decision"] = "promote_champion"
        reasons.append("ladder_promoted_candidate")
    else:
        reasons.append("ladder_no_promotion")
    return judgement


def _result_checkpoint_value(result: dict[str, Any]) -> str:
    for key in ("best_checkpoint", "latest_checkpoint", "checkpoint_path"):
        value = str(result.get(key, "")).strip()
        if value:
            return value
    suggestion = _mapping(result.get("suggested_ladder_submission"))
    return str(suggestion.get("checkpoint_path", "")).strip()


def _result_config_path(result: dict[str, Any]) -> str:
    suggestion = _mapping(result.get("suggested_ladder_submission"))
    return str(suggestion.get("config_path") or result.get("config_path", "")).strip()


def _write_ladder_manifest(
    path: Path,
    *,
    repo_root: Path,
    request_id: str,
    submission_id: str,
    checkpoint_path: Path,
    candidate_config_path: Path | None,
) -> None:
    manifest_dir = path.parent.resolve()
    champion_config = _relative_path_for_toml(manifest_dir, repo_root / "configs" / "local_4h_strongest_v2_gumbel.toml")
    champion_checkpoint = _relative_path_for_toml(manifest_dir, repo_root / "models" / "production" / "hex6_champion.pt")
    candidate_checkpoint = _relative_path_for_toml(manifest_dir, checkpoint_path)
    candidate_config = _relative_path_for_toml(manifest_dir, candidate_config_path) if candidate_config_path is not None else ""
    lines = [
        f"# Generated from autopilot result {request_id}.",
        "",
        "[champion]",
        'submission_id = "champion_production"',
        'name = "Production Champion"',
        'kind = "checkpoint"',
        "slot = 0",
        f"config_path = {_toml_string(champion_config)}",
        f"checkpoint_path = {_toml_string(champion_checkpoint)}",
        'notes = "Current production champion used as incumbent."',
        "",
        "[[submissions]]",
        f"submission_id = {_toml_string(submission_id)}",
        f"name = {_toml_string('Autopilot ' + request_id)}",
        'kind = "checkpoint"',
        "slot = 1",
    ]
    if candidate_config:
        lines.append(f"config_path = {_toml_string(candidate_config)}")
    lines.extend(
        [
            f"checkpoint_path = {_toml_string(candidate_checkpoint)}",
            f"notes = {_toml_string('Autopilot-returned training candidate from ' + request_id + '.')}",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="ascii")


def _safe_identifier(value: str) -> str:
    identifier = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip()).strip("_").lower()
    return identifier or "result"


def _relative_path_for_toml(base_dir: Path, target: Path) -> str:
    return Path(_repo_relative_text(base_dir, target)).as_posix()


def _repo_relative_text(base_dir: Path, target: Path) -> str:
    try:
        return str(target.resolve().relative_to(base_dir.resolve())).replace("\\", "/")
    except ValueError:
        return str(Path(_relative_path(base_dir.resolve(), target.resolve()))).replace("\\", "/")


def _repo_relative_or_absolute(repo_root: Path, target: Path) -> str:
    try:
        return target.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(target.resolve())


def _relative_path(base_dir: Path, target: Path) -> Path:
    try:
        return Path(target).resolve().relative_to(base_dir.resolve())
    except ValueError:
        import os

        return Path(os.path.relpath(target.resolve(), base_dir.resolve()))


def _toml_string(value: str) -> str:
    return json.dumps(value)


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


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
