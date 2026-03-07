from pathlib import Path

from hex6.config import load_config
from hex6.integration.status import FileStatusTransport, RunContext, StatusPublisher
from hex6.train.bootstrap import train_bootstrap


def test_file_status_publisher_writes_latest_and_history(tmp_path: Path) -> None:
    publisher = StatusPublisher(
        transport=FileStatusTransport(tmp_path),
        context=RunContext(
            run_id="run-123",
            project_name="hex6",
            phase="test",
            config_path="configs/fast.toml",
            output_dir="artifacts/test",
            backend="file",
            host="local",
            started_at="2026-03-07T00:00:00Z",
        ),
        latest_path="status/latest.json",
        run_history_path="status/runs",
    )

    publisher.publish({"stage": "starting"})
    payload = publisher.publish({"stage": "complete", "epochs": 1})

    latest = (tmp_path / "status" / "latest.json").read_text(encoding="ascii")
    history = (tmp_path / "status" / "runs" / "run-123.json").read_text(encoding="ascii")

    assert "\"stage\": \"complete\"" in latest
    assert "\"run_id\": \"run-123\"" in history
    assert payload["sequence"] == 2


def test_train_bootstrap_reports_progress_callback(tmp_path: Path) -> None:
    config = load_config("configs/fast.toml")
    events: list[dict[str, object]] = []

    metrics = train_bootstrap(
        config,
        output_dir=tmp_path / "bootstrap",
        config_path="configs/fast.toml",
        progress_callback=events.append,
    )

    assert events[0]["stage"] == "starting"
    assert events[-1]["stage"] == "complete"
    assert events[-1]["checkpoint"] == metrics["checkpoint"]
