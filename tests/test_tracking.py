from pathlib import Path

from hex6.config import load_config
from hex6.train.tracking import NullExperimentTracker, _sanitize, build_experiment_tracker


def test_build_experiment_tracker_defaults_to_null(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HEX6_ENABLE_WANDB", raising=False)
    tracker = build_experiment_tracker(
        load_config("configs/fast.toml"),
        config_path="configs/fast.toml",
        output_dir=tmp_path,
        run_id="test-run",
        job_type="bootstrap",
    )
    assert isinstance(tracker, NullExperimentTracker)


def test_sanitize_converts_paths_and_nested_values() -> None:
    payload = {
        "path": Path("artifacts/example"),
        "nested": {"items": (1, Path("foo"))},
    }

    sanitized = _sanitize(payload)

    assert sanitized == {
        "path": "artifacts\\example",
        "nested": {"items": [1, "foo"]},
    }
