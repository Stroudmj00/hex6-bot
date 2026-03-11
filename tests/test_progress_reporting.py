from datetime import datetime, timezone

from hex6.train.progress_reporting import (
    BootstrapProgressReporter,
    CycleProgressReporter,
    bootstrap_progress_fraction,
)


def test_bootstrap_progress_fraction_tracks_core_stages() -> None:
    assert bootstrap_progress_fraction({"stage": "starting"}, include_evaluation=True) == 0.0
    assert bootstrap_progress_fraction(
        {"stage": "self_play", "completed_games": 3, "total_games": 6},
        include_evaluation=True,
    ) == 0.35
    assert bootstrap_progress_fraction(
        {"stage": "training", "epoch": 2, "epochs": 4},
        include_evaluation=True,
    ) == 0.835
    assert bootstrap_progress_fraction({"stage": "complete"}, include_evaluation=True) == 1.0


def test_bootstrap_progress_reporter_enriches_payload(monkeypatch) -> None:
    monkeypatch.setattr("hex6.train.progress_reporting.time.monotonic", lambda: 10.0)
    reporter = BootstrapProgressReporter(
        publish=None,
        include_evaluation=True,
        started_monotonic=0.0,
        started_wall_time=datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc),
    )

    enriched = reporter.handle(
        {"stage": "self_play", "completed_games": 3, "total_games": 6}
    )

    assert enriched["progress_percent"] == 35.0
    assert enriched["estimated_remaining_seconds"] is not None
    assert isinstance(enriched["estimated_completion_time"], str)


def test_cycle_progress_reporter_reports_cycle_and_run_percent(monkeypatch) -> None:
    monkeypatch.setattr("hex6.train.progress_reporting.time.monotonic", lambda: 20.0)
    reporter = CycleProgressReporter(
        publish=None,
        max_cycles=4,
        time_budget_seconds=None,
        started_monotonic=0.0,
        started_wall_time=datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc),
        current_cycle_index=1,
        current_cycle_started_monotonic=0.0,
    )

    enriched = reporter.handle(
        {
            "cycle_index": 1,
            "cycle_phase": "training",
            "stage": "training",
            "progress_fraction": 0.5,
            "epoch": 1,
            "epochs": 2,
        }
    )

    assert enriched["cycle_progress_percent"] == 35.0
    assert enriched["run_progress_percent"] == 8.8
    assert isinstance(enriched["estimated_completion_time"], str)
