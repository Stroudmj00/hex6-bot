from dataclasses import replace
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

from hex6.config import load_config
from hex6.integration.status import FileStatusTransport, RunContext, StatusPublisher, resolve_github_token
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


def test_resolve_github_token_reads_colab_userdata(monkeypatch) -> None:
    monkeypatch.delenv("HEX6_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("hex6.integration.status._find_gh_cli", lambda: None)
    google_module = ModuleType("google")
    colab_module = ModuleType("google.colab")
    colab_module.userdata = SimpleNamespace(get=lambda name: "secret-token" if name == "HEX6_GITHUB_TOKEN" else "")
    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.colab", colab_module)

    assert resolve_github_token(require=True) == "secret-token"


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
    assert metrics["self_play_workers"] == config.training.self_play_workers
    assert "self_play_seconds" in metrics


def test_train_bootstrap_parallel_self_play_runs(tmp_path: Path) -> None:
    config = load_config("configs/fast.toml")
    config = replace(
        config,
        training=replace(
            config.training,
            bootstrap_strategy="search_supervision_then_self_play",
            bootstrap_games=2,
            max_game_plies=6,
            policy_target="all_placements",
            self_play_workers=2,
            data_loader_workers=0,
        ),
    )

    metrics = train_bootstrap(
        config,
        output_dir=tmp_path / "parallel-bootstrap",
        config_path="configs/fast.toml",
    )

    assert metrics["examples"] > 0
    assert metrics["self_play_workers"] == 2
