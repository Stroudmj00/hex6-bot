import json
from pathlib import Path
import subprocess
import zipfile

from hex6.integration.autopilot import (
    build_request_result,
    build_research_prompt,
    claim_next_job_request,
    claim_next_research_idea,
    complete_job_request,
    complete_research_idea,
    export_result_bundle,
    judge_request_result,
    list_job_requests,
    load_autopilot_config,
    promote_champion_from_ladder,
    read_research_state,
    run_worker_loop,
    submit_job_request,
)


def _write_plan(tmp_path: Path) -> Path:
    backlog_path = tmp_path / "colab_research_backlog.toml"
    backlog_path.write_text(
        "\n".join(
            [
                "[[ideas]]",
                'idea_id = "IDEA-100"',
                'title = "Top idea"',
                "priority = 100",
                'summary = "Study the next engine change."',
                'deliverable = "Write a short proposal."',
                'source_refs = ["docs/literature-roadmap.md"]',
                "",
                "[[ideas]]",
                'idea_id = "IDEA-050"',
                'title = "Second idea"',
                "priority = 50",
                'summary = "Lower priority follow-up."',
                "",
            ]
        ),
        encoding="ascii",
    )
    plan_path = tmp_path / "colab_autopilot.toml"
    plan_path.write_text(
        "\n".join(
            [
                "[autopilot]",
                'name = "test_autopilot"',
                'request_dir = "artifacts/requests"',
                'result_dir = "artifacts/results"',
                'state_path = "artifacts/state.json"',
                'default_status_backend = "none"',
                'default_run_prefix = "autotest"',
                "poll_seconds = 5.0",
                "default_job_timeout_minutes = 15.0",
                f'research_backlog_path = "{backlog_path.name}"',
                'research_state_path = "artifacts/research_state.json"',
                'research_note_dir = "artifacts/research_notes"',
                "",
            ]
        ),
        encoding="ascii",
    )
    return plan_path


def test_submit_and_list_job_request(tmp_path: Path) -> None:
    plan_path = _write_plan(tmp_path)
    config = load_autopilot_config(plan_path)

    submit_job_request(
        config,
        request_id="cycle_smoke",
        kind="cycle",
        priority=90,
        notes="smoke cycle",
        options={
            "config": "configs/colab_strongest_v2.toml",
            "output_root": "artifacts/bootstrap_colab_strongest_v2",
            "minutes": 60,
        },
    )

    rows = list_job_requests(config)

    assert len(rows) == 1
    assert rows[0]["request_id"] == "cycle_smoke"
    assert rows[0]["kind"] == "cycle"
    assert rows[0]["status"] == "pending"


def test_load_autopilot_config_resolves_repo_root_relative_paths_from_configs_dir(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    configs_dir = repo_root / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)
    (configs_dir / "colab_research_backlog.toml").write_text("", encoding="ascii")
    plan_path = configs_dir / "colab_autopilot.toml"
    plan_path.write_text(
        "\n".join(
            [
                "[autopilot]",
                'request_dir = "artifacts/requests"',
                'result_dir = "artifacts/results"',
                'state_path = "artifacts/state.json"',
                'research_backlog_path = "configs/colab_research_backlog.toml"',
                'research_state_path = "artifacts/research_state.json"',
                'research_note_dir = "artifacts/research_notes"',
                "",
            ]
        ),
        encoding="ascii",
    )

    config = load_autopilot_config(plan_path)

    assert Path(config.request_dir) == (repo_root / "artifacts" / "requests").resolve()
    assert Path(config.result_dir) == (repo_root / "artifacts" / "results").resolve()
    assert Path(config.research_backlog_path) == (repo_root / "configs" / "colab_research_backlog.toml").resolve()


def test_claim_and_complete_cycle_request_writes_return_payload(tmp_path: Path) -> None:
    plan_path = _write_plan(tmp_path)
    config = load_autopilot_config(plan_path)
    repo_root = tmp_path
    config_dir = repo_root / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "colab_strongest_v2.toml").write_text("", encoding="ascii")
    output_root = repo_root / "artifacts" / "bootstrap_colab_strongest_v2"
    output_root.mkdir(parents=True, exist_ok=True)
    cycle_dir = output_root / "cycle_001"
    cycle_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = cycle_dir / "bootstrap_model.pt"
    checkpoint_path.write_text("checkpoint", encoding="ascii")
    (output_root / "cycle_summary.json").write_text(
        json.dumps(
            {
                "latest_checkpoint": "artifacts/bootstrap_colab_strongest_v2/cycle_001/bootstrap_model.pt",
                "best_checkpoint": "artifacts/bootstrap_colab_strongest_v2/cycle_001/bootstrap_model.pt",
            },
            indent=2,
        ),
        encoding="ascii",
    )

    submit_job_request(
        config,
        request_id="cycle_candidate",
        kind="cycle",
        priority=95,
        options={
            "config": "configs/colab_strongest_v2.toml",
            "output_root": "artifacts/bootstrap_colab_strongest_v2",
            "minutes": 60,
        },
    )

    request = claim_next_job_request(config, worker_id="worker-01", run_id="autotest-cycle_candidate-20260524-220000")
    assert request is not None

    result_payload = build_request_result(config, request, repo_root=repo_root)
    result_path = complete_job_request(
        config,
        request_id=request.request_id,
        success=True,
        exit_code=0,
        result_payload=result_payload,
    )

    payload = json.loads(result_path.read_text(encoding="ascii"))
    assert payload["request"]["status"] == "completed"
    assert payload["result"]["best_checkpoint"] == "artifacts/bootstrap_colab_strongest_v2/cycle_001/bootstrap_model.pt"
    assert payload["result"]["suggested_ladder_submission"]["kind"] == "checkpoint"
    assert payload["result"]["config_path"] == "configs/colab_strongest_v2.toml"


def test_judge_cycle_result_writes_ladder_manifest_and_request(tmp_path: Path) -> None:
    plan_path = _write_plan(tmp_path)
    config = load_autopilot_config(plan_path)
    config_dir = tmp_path / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "colab_strongest_v2.toml").write_text("", encoding="ascii")
    checkpoint = tmp_path / "artifacts" / "bootstrap_colab_strongest_v2" / "cycle_001" / "bootstrap_model.pt"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text("checkpoint", encoding="ascii")
    result_path = tmp_path / "artifacts" / "results" / "cycle_candidate.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(
            {
                "request": {
                    "request_id": "cycle_candidate",
                    "kind": "cycle",
                    "status": "completed",
                    "exit_code": 0,
                },
                "result": {
                    "kind": "cycle",
                    "best_checkpoint": "artifacts/bootstrap_colab_strongest_v2/cycle_001/bootstrap_model.pt",
                    "config_path": "configs/colab_strongest_v2.toml",
                    "suggested_ladder_submission": {
                        "kind": "checkpoint",
                        "config_path": "configs/colab_strongest_v2.toml",
                        "checkpoint_path": "artifacts/bootstrap_colab_strongest_v2/cycle_001/bootstrap_model.pt",
                    },
                },
            },
            indent=2,
        ),
        encoding="ascii",
    )

    judgement = judge_request_result(
        config,
        result_path,
        submit_ladder=True,
        ladder_request_id="ladder_cycle_candidate",
    )

    assert judgement["decision"] == "submit_ladder"
    assert Path(judgement["ladder_manifest_path"]).exists()
    assert judgement["ladder_request_id"] == "ladder_cycle_candidate"
    rows = list_job_requests(config)
    ladder = next(row for row in rows if row["request_id"] == "ladder_cycle_candidate")
    assert ladder["kind"] == "ladder"
    assert ladder["options"]["manifest"] == "artifacts/ladder_manifests/cycle_candidate.toml"
    manifest_text = Path(judgement["ladder_manifest_path"]).read_text(encoding="ascii")
    assert 'submission_id = "autopilot_cycle_candidate"' in manifest_text
    assert "bootstrap_colab_strongest_v2/cycle_001/bootstrap_model.pt" in manifest_text


def test_judge_failed_result_archives_without_ladder_request(tmp_path: Path) -> None:
    plan_path = _write_plan(tmp_path)
    config = load_autopilot_config(plan_path)
    result_path = tmp_path / "artifacts" / "results" / "failed_cycle.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(
            {
                "request": {
                    "request_id": "failed_cycle",
                    "kind": "cycle",
                    "status": "failed",
                    "exit_code": 1,
                },
                "result": {},
            },
            indent=2,
        ),
        encoding="ascii",
    )

    judgement = judge_request_result(config, result_path, submit_ladder=True)

    assert judgement["decision"] == "archive"
    assert "request_status_failed" in judgement["reasons"]
    assert list_job_requests(config) == []


def test_export_result_bundle_includes_result_checkpoint_and_log(tmp_path: Path) -> None:
    plan_path = _write_plan(tmp_path)
    config = load_autopilot_config(plan_path)
    config_dir = tmp_path / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "colab_strongest_v2.toml").write_text("", encoding="ascii")
    checkpoint = tmp_path / "artifacts" / "bootstrap_colab_strongest_v2" / "cycle_001" / "bootstrap_model.pt"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text("checkpoint", encoding="ascii")
    (checkpoint.parent / "metrics.json").write_text(json.dumps({"examples": 4}), encoding="ascii")
    summary_path = tmp_path / "artifacts" / "bootstrap_colab_strongest_v2" / "cycle_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "latest_checkpoint": "artifacts/bootstrap_colab_strongest_v2/cycle_001/bootstrap_model.pt",
                "best_checkpoint": "artifacts/bootstrap_colab_strongest_v2/cycle_001/bootstrap_model.pt",
                "cycles": [{"metrics": {"checkpoint": "artifacts/bootstrap_colab_strongest_v2/cycle_001/bootstrap_model.pt"}}],
            },
            indent=2,
        ),
        encoding="ascii",
    )
    worker_log = tmp_path / "artifacts" / "colab_autopilot" / "worker.log"
    worker_log.parent.mkdir(parents=True, exist_ok=True)
    worker_log.write_text("worker output", encoding="ascii")
    result_path = tmp_path / "artifacts" / "results" / "cycle_candidate.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(
            {
                "request": {
                    "request_id": "cycle_candidate",
                    "kind": "cycle",
                    "status": "completed",
                    "exit_code": 0,
                },
                "result": {
                    "kind": "cycle",
                    "summary_path": "artifacts/bootstrap_colab_strongest_v2/cycle_summary.json",
                    "best_checkpoint": "artifacts/bootstrap_colab_strongest_v2/cycle_001/bootstrap_model.pt",
                    "config_path": "configs/colab_strongest_v2.toml",
                },
            },
            indent=2,
        ),
        encoding="ascii",
    )

    bundle = export_result_bundle(config, result_path, repo_root=tmp_path)

    assert Path(bundle["bundle_path"]).exists()
    with zipfile.ZipFile(bundle["bundle_path"]) as archive:
        names = set(archive.namelist())
    assert "bundle_manifest.json" in names
    assert "artifacts/results/cycle_candidate.json" in names
    assert "artifacts/bootstrap_colab_strongest_v2/cycle_summary.json" in names
    assert "artifacts/bootstrap_colab_strongest_v2/cycle_001/bootstrap_model.pt" in names
    assert "artifacts/bootstrap_colab_strongest_v2/cycle_001/metrics.json" in names
    assert "artifacts/colab_autopilot/worker.log" in names


def test_worker_marks_timed_out_job_failed_and_exports_bundle(tmp_path: Path, monkeypatch) -> None:
    plan_path = _write_plan(tmp_path)
    config = load_autopilot_config(plan_path)
    submit_job_request(
        config,
        request_id="timeout_cycle",
        kind="cycle",
        priority=90,
        options={
            "config": "configs/colab_strongest_v2.toml",
            "output_root": "artifacts/bootstrap_timeout",
            "timeout_minutes": 0.01,
        },
    )
    seen: dict[str, object] = {}

    def fake_run(command, *, cwd, check, timeout):
        seen["command"] = command
        seen["cwd"] = cwd
        seen["check"] = check
        seen["timeout"] = timeout
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr("hex6.integration.autopilot.subprocess.run", fake_run)

    run_worker_loop(
        config,
        repo_root=tmp_path,
        python_exe="python",
        worker_id="worker-01",
        once=True,
    )

    assert seen["timeout"] == 0.6
    rows = list_job_requests(config)
    failed = next(row for row in rows if row["request_id"] == "timeout_cycle")
    assert failed["status"] == "failed"
    assert failed["exit_code"] == 124
    assert "timed out" in failed["error"]
    result_path = Path(config.result_dir) / "timeout_cycle.json"
    result = json.loads(result_path.read_text(encoding="ascii"))
    assert result["result"]["timed_out"] is True
    assert result["result"]["timeout_minutes"] == 0.01
    assert (Path(config.result_dir).parent / "exports" / "timeout_cycle.zip").exists()


def test_worker_fails_fast_when_colab_drive_output_is_not_mounted(tmp_path: Path, monkeypatch) -> None:
    plan_path = _write_plan(tmp_path)
    config = load_autopilot_config(plan_path)
    submit_job_request(
        config,
        request_id="drive_cycle",
        kind="cycle",
        priority=95,
        options={
            "config": "configs/colab_strongest_v2.toml",
            "output_root": "/content/drive/MyDrive/hex6_colab_autopilot/runs/drive_cycle",
            "timeout_minutes": 120,
        },
    )

    def fake_run(*args, **kwargs):
        raise AssertionError("worker should not launch training when Drive output is unavailable")

    monkeypatch.setattr("hex6.integration.autopilot.subprocess.run", fake_run)

    run_worker_loop(
        config,
        repo_root=tmp_path,
        python_exe="python",
        worker_id="worker-01",
        once=True,
    )

    rows = list_job_requests(config)
    failed = next(row for row in rows if row["request_id"] == "drive_cycle")
    assert failed["status"] == "failed"
    assert failed["exit_code"] == 78
    assert "storage preflight failed" in failed["error"]
    assert "/content/drive is not mounted" in failed["error"]
    result_path = Path(config.result_dir) / "drive_cycle.json"
    result = json.loads(result_path.read_text(encoding="ascii"))
    preflight = result["result"]["storage_preflight"]
    assert preflight["ok"] is False
    assert preflight["checks"][0]["raw_path"].startswith("/content/drive/MyDrive/")
    assert (Path(config.result_dir).parent / "exports" / "drive_cycle.zip").exists()


def test_promote_champion_from_ladder_requires_promoted_submission(tmp_path: Path) -> None:
    summary_path = tmp_path / "ladder_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "manifest_path": str(tmp_path / "manifest.toml"),
                "champion": {"submission_id": "champion", "checkpoint_path": "champion.pt"},
                "promoted_submission_ids": [],
            },
            indent=2,
        ),
        encoding="ascii",
    )

    result = promote_champion_from_ladder(summary_path)

    assert result["decision"] == "no_promotion"
    assert result["applied"] is False
    assert result["reason"] == "ladder_summary_has_no_promotions"


def test_promote_champion_from_ladder_copies_checkpoint_and_metadata(tmp_path: Path) -> None:
    manifest_path = tmp_path / "ladder" / "manifest.toml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("# manifest\n", encoding="ascii")
    checkpoint_path = tmp_path / "candidate.pt"
    checkpoint_path.write_text("candidate checkpoint", encoding="ascii")
    summary_path = tmp_path / "ladder" / "ladder_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "manifest_path": str(manifest_path),
                "champion": {
                    "submission_id": "candidate",
                    "name": "Candidate",
                    "kind": "checkpoint",
                    "checkpoint_path": "../candidate.pt",
                },
                "promoted_submission_ids": ["candidate"],
            },
            indent=2,
        ),
        encoding="ascii",
    )
    production_checkpoint = tmp_path / "models" / "production" / "hex6_champion.pt"
    metadata_path = tmp_path / "models" / "production" / "hex6_champion.metadata.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps({"source_checkpoint": "old.pt"}, indent=2), encoding="ascii")

    dry_run = promote_champion_from_ladder(
        summary_path,
        production_checkpoint_path=production_checkpoint,
        metadata_path=metadata_path,
    )
    applied = promote_champion_from_ladder(
        summary_path,
        production_checkpoint_path=production_checkpoint,
        metadata_path=metadata_path,
        apply=True,
    )

    assert dry_run["decision"] == "promote_champion"
    assert dry_run["applied"] is False
    assert production_checkpoint.read_text(encoding="ascii") == "candidate checkpoint"
    metadata = json.loads(metadata_path.read_text(encoding="ascii"))
    assert applied["applied"] is True
    assert metadata["promoted_submission_id"] == "candidate"
    assert metadata["previous_metadata"]["source_checkpoint"] == "old.pt"


def test_claim_next_research_idea_and_complete_it(tmp_path: Path) -> None:
    plan_path = _write_plan(tmp_path)
    config = load_autopilot_config(plan_path)

    idea = claim_next_research_idea(config, researcher_id="codex-research-01")

    assert idea is not None
    assert idea.idea_id == "IDEA-100"
    prompt = build_research_prompt(idea)
    assert "IDEA-100" in prompt
    assert "Top idea" in prompt

    complete_research_idea(
        config,
        idea_id=idea.idea_id,
        note_path="artifacts/colab_autopilot/research_notes/IDEA-100.md",
    )
    state = read_research_state(config.research_state_path)
    assert idea.idea_id in state["completed"]
