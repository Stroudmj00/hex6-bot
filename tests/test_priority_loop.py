from datetime import datetime, timezone

from hex6.integration.run_priority_loop import (
    JobSpec,
    QueueConfig,
    build_job_command,
    build_run_id,
    choose_next_job,
)


def test_choose_next_job_picks_highest_priority_eligible() -> None:
    queue = QueueConfig(
        name="test",
        idle_sleep_seconds=10.0,
        post_job_pause_seconds=0.0,
        default_status_backend="github_branch",
        default_run_prefix="colabq",
        jobs=(
            JobSpec("low", "bootstrap", 10, True, 0.0, {"config": "configs/colab.toml", "output": "artifacts/a"}),
            JobSpec("high", "cycle", 100, True, 0.0, {"config": "configs/colab_hour.toml", "output_root": "artifacts/b", "minutes": 60}),
        ),
    )
    state = {"jobs": {}, "history": []}
    now = datetime(2026, 3, 8, 4, 0, 0, tzinfo=timezone.utc)

    job, wait_seconds = choose_next_job(queue, state, now=now)

    assert job is not None
    assert job.job_id == "high"
    assert wait_seconds == 0.0


def test_choose_next_job_obeys_min_interval() -> None:
    queue = QueueConfig(
        name="test",
        idle_sleep_seconds=5.0,
        post_job_pause_seconds=0.0,
        default_status_backend="github_branch",
        default_run_prefix="colabq",
        jobs=(
            JobSpec("primary", "cycle", 100, True, 30.0, {"config": "configs/colab_hour.toml", "output_root": "artifacts/x", "minutes": 60}),
        ),
    )
    now = datetime(2026, 3, 8, 4, 0, 0, tzinfo=timezone.utc)
    state = {
        "jobs": {
            "primary": {
                "runs": 1,
                "successes": 1,
                "failures": 0,
                "last_started_at": "2026-03-08T03:40:00Z",
                "last_completed_at": "2026-03-08T03:45:00Z",
                "last_success_at": "2026-03-08T03:45:00Z",
                "last_failed_at": "",
                "last_exit_code": 0,
                "last_run_id": "x",
            }
        },
        "history": [],
    }

    job, wait_seconds = choose_next_job(queue, state, now=now)

    assert job is None
    # Next allowed is 04:15:00Z.
    assert 890.0 <= wait_seconds <= 910.0


def test_choose_next_job_respects_max_consecutive_runs() -> None:
    queue = QueueConfig(
        name="test",
        idle_sleep_seconds=5.0,
        post_job_pause_seconds=0.0,
        default_status_backend="github_branch",
        default_run_prefix="colabq",
        jobs=(
            JobSpec("cycle_main", "cycle", 100, True, 0.0, {"max_consecutive_runs": 2}),
            JobSpec("tournament", "tournament", 80, True, 0.0, {}),
        ),
    )
    state = {
        "jobs": {},
        "history": [],
        "scheduler": {"last_job_id": "cycle_main", "consecutive_runs": 2},
    }
    now = datetime(2026, 3, 8, 4, 0, 0, tzinfo=timezone.utc)

    job, wait_seconds = choose_next_job(queue, state, now=now)

    assert job is not None
    assert job.job_id == "tournament"
    assert wait_seconds == 0.0


def test_build_job_command_tournament_includes_priority_settings() -> None:
    job = JobSpec(
        job_id="tournament_regression",
        kind="tournament",
        priority=80,
        enabled=True,
        min_interval_minutes=0.0,
        options={
            "config": "configs/fast.toml",
            "output": "artifacts/tournament_colab",
            "games_per_match": 2,
            "max_game_plies": 100,
            "max_checkpoints": 3,
            "checkpoint_glob": "artifacts/**/bootstrap_model.pt",
            "include_baseline": True,
            "include_random": False,
            "random_seed": 7,
        },
    )

    command = build_job_command(
        job,
        python_exe="python",
        run_id="colabq-tournament_regression-20260308-040000",
        status_backend="github_branch",
    )

    joined = " ".join(command)
    assert "hex6.eval.run_tournament" in joined
    assert "--max-game-plies 100" in joined
    assert "--status-backend github_branch" in joined
    assert "--no-include-random" in command


def test_build_run_id_contains_job_and_prefix() -> None:
    now = datetime(2026, 3, 8, 4, 0, 0, tzinfo=timezone.utc)
    run_id = build_run_id("colabq", "cycle_main", now=now)
    assert run_id == "colabq-cycle_main-20260308-040000"
