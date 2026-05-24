import json
from pathlib import Path

from hex6.config import load_config
from hex6.eval.arena import AgentSpec
from hex6.eval.ladder import (
    LadderSubmission,
    ResolvedLadderAgent,
    append_strength_ledger,
    evaluate_ladder_candidate,
    load_ladder_manifest,
    resolve_ladder_agent,
    run_ladder,
    run_ladder_gate,
)


def _resolved_agent(config, submission_id: str, name: str) -> ResolvedLadderAgent:
    submission = LadderSubmission(
        submission_id=submission_id,
        name=name,
        kind="baseline",
    )
    agent = AgentSpec(
        name=name,
        kind="baseline",
        choose_turn=lambda state, play_config: object(),
        play_config=config,
    )
    return ResolvedLadderAgent(
        submission=submission,
        agent=agent,
        config_path="configs/colab_ladder.toml",
        checkpoint_path=None,
    )


def test_load_ladder_manifest_reads_champion_and_submissions(tmp_path: Path) -> None:
    manifest_path = tmp_path / "ladder.toml"
    manifest_path.write_text(
        "\n".join(
            [
                "[champion]",
                'submission_id = "champion"',
                'name = "Champion"',
                'kind = "baseline"',
                "",
                "[[submissions]]",
                'submission_id = "slot_01"',
                'name = "Slot 01"',
                'kind = "random"',
                "random_seed = 5",
                "",
            ]
        ),
        encoding="ascii",
    )

    manifest = load_ladder_manifest(manifest_path)

    assert manifest.champion.submission_id == "champion"
    assert manifest.champion.kind == "baseline"
    assert len(manifest.submissions) == 1
    assert manifest.submissions[0].submission_id == "slot_01"
    assert manifest.submissions[0].kind == "random"
    assert manifest.submissions[0].random_seed == 5


def test_resolve_ladder_agent_applies_submission_config_override(tmp_path: Path) -> None:
    base_config = load_config("configs/colab_ladder.toml")
    override_path = tmp_path / "submission.toml"
    override_text = Path("configs/colab_ladder.toml").read_text(encoding="ascii").replace(
        "root_simulations = 96",
        "root_simulations = 144",
        1,
    )
    override_path.write_text(override_text, encoding="ascii")
    submission = LadderSubmission(
        submission_id="slot_03",
        name="Config Override",
        kind="baseline",
        config_path=str(override_path),
    )

    resolved = resolve_ladder_agent(
        submission,
        base_eval_config=base_config,
        reference_path=tmp_path / "manifest.toml",
    )

    assert resolved.agent.play_config is not None
    assert resolved.agent.play_config.search.root_simulations == 144
    assert resolved.agent.play_config.game == base_config.game
    assert resolved.config_path == str(override_path.resolve())


def test_run_ladder_gate_requires_even_games_for_balanced_sides(tmp_path: Path) -> None:
    config = load_config("configs/colab_ladder.toml")
    challenger = _resolved_agent(config, "challenger", "Challenger")
    incumbent = _resolved_agent(config, "incumbent", "Incumbent")

    try:
        run_ladder_gate(
            challenger=challenger,
            incumbent=incumbent,
            config=config,
            output_dir=tmp_path / "gate",
            games=9,
            required_points=9.0,
            rung_index=1,
            phase="gate",
        )
    except ValueError as exc:
        assert "even game count" in str(exc)
    else:
        raise AssertionError("expected balanced-side ladder gate to reject odd game counts")


def test_run_ladder_gate_writes_balanced_empty_board_summary(tmp_path: Path, monkeypatch) -> None:
    config = load_config("configs/colab_ladder.toml")
    challenger = _resolved_agent(config, "challenger", "Challenger")
    incumbent = _resolved_agent(config, "incumbent", "Incumbent")

    monkeypatch.setattr(
        "hex6.eval.ladder.run_arena",
        lambda **_kwargs: {
            "agent_a": {"name": "Challenger"},
            "agent_b": {"name": "Incumbent"},
            "score_a": 9.0,
            "score_b": 1.0,
            "wins_a": 8,
            "wins_b": 0,
            "draws": 2,
            "draw_rate": 0.2,
            "game_history": [
                {"x_agent": "Challenger", "o_agent": "Incumbent"},
                {"x_agent": "Incumbent", "o_agent": "Challenger"},
            ]
            * 5,
        },
    )

    summary = run_ladder_gate(
        challenger=challenger,
        incumbent=incumbent,
        config=config,
        output_dir=tmp_path / "gate",
        games=10,
        required_points=9.0,
        rung_index=1,
        phase="gate",
    )

    assert summary["passed"] is True
    assert summary["balanced_sides"] is True
    assert summary["empty_board_only"] is True
    assert Path(summary["summary_path"]).exists()


def test_append_strength_ledger_appends_jsonl_entries(tmp_path: Path) -> None:
    ledger_path = tmp_path / "strength_ledger.jsonl"

    append_strength_ledger(ledger_path, {"rung_index": 1, "promoted": False})
    append_strength_ledger(ledger_path, {"rung_index": 2, "promoted": True})

    lines = ledger_path.read_text(encoding="ascii").splitlines()

    assert len(lines) == 2
    assert json.loads(lines[0])["rung_index"] == 1
    assert json.loads(lines[1])["promoted"] is True


def test_evaluate_ladder_candidate_requires_confirmation(tmp_path: Path, monkeypatch) -> None:
    config = load_config("configs/colab_ladder.toml")
    challenger = _resolved_agent(config, "challenger", "Challenger")
    incumbent = _resolved_agent(config, "incumbent", "Incumbent")
    phases: list[str] = []

    def fake_run_ladder_gate(*, phase, **_kwargs):
        phases.append(phase)
        if phase == "gate":
            return {"phase": phase, "passed": True, "challenger_points": 9.0}
        return {"phase": phase, "passed": False, "challenger_points": 8.5}

    monkeypatch.setattr("hex6.eval.ladder.run_ladder_gate", fake_run_ladder_gate)

    result = evaluate_ladder_candidate(
        challenger=challenger,
        incumbent=incumbent,
        config=config,
        output_dir=tmp_path / "ladder_eval",
        rung_index=1,
    )

    assert phases == ["gate", "confirmation"]
    assert result["promoted"] is False
    assert result["reason"] == "confirmation_failed"
    assert result["confirmation"]["passed"] is False


def test_evaluate_ladder_candidate_uses_adaptive_extra_compute_for_near_miss(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = load_config("configs/colab_ladder.toml")
    challenger = _resolved_agent(config, "challenger", "Challenger")
    incumbent = _resolved_agent(config, "incumbent", "Incumbent")
    observed_root_sims: dict[str, tuple[int, int]] = {}

    def fake_run_ladder_gate(*, challenger, incumbent, phase, **_kwargs):
        observed_root_sims[phase] = (
            challenger.agent.play_config.search.root_simulations,
            incumbent.agent.play_config.search.root_simulations,
        )
        if phase == "gate":
            return {"phase": phase, "passed": False, "challenger_points": 8.0}
        return {"phase": phase, "passed": True, "challenger_points": 9.0}

    monkeypatch.setattr("hex6.eval.ladder.run_ladder_gate", fake_run_ladder_gate)

    result = evaluate_ladder_candidate(
        challenger=challenger,
        incumbent=incumbent,
        config=config,
        output_dir=tmp_path / "ladder_adaptive",
        rung_index=2,
    )

    assert result["promoted"] is True
    assert result["reason"] == "promoted_after_adaptive"
    assert observed_root_sims["gate"] == (96, 96)
    assert observed_root_sims["adaptive_gate"] == (128, 128)
    assert observed_root_sims["confirmation"] == (128, 128)


def test_run_ladder_resumes_and_skips_processed_submissions(tmp_path: Path, monkeypatch) -> None:
    config = load_config("configs/colab_ladder.toml")
    manifest_path = tmp_path / "ladder.toml"
    manifest_path.write_text(
        "\n".join(
            [
                "[champion]",
                'submission_id = "champion"',
                'name = "Champion"',
                'kind = "baseline"',
                "",
                "[[submissions]]",
                'submission_id = "slot_01"',
                'name = "Slot 01"',
                'kind = "baseline"',
                "",
                "[[submissions]]",
                'submission_id = "slot_02"',
                'name = "Slot 02"',
                'kind = "random"',
                "random_seed = 7",
                "",
            ]
        ),
        encoding="ascii",
    )
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "champion": {
                    "submission_id": "champion",
                    "name": "Champion",
                    "kind": "baseline",
                    "config_path": "",
                    "checkpoint_path": "",
                    "notes": "",
                    "slot": 0,
                    "random_seed": 0,
                    "random_candidate_width": 24,
                },
                "processed_submission_ids": ["slot_01"],
                "promoted_submission_ids": [],
                "results": [
                    {
                        "rung_index": 1,
                        "promoted": False,
                        "reason": "gate_failed",
                    }
                ],
            },
            indent=2,
        ),
        encoding="ascii",
    )
    evaluated: list[str] = []

    def fake_evaluate_ladder_candidate(*, challenger, incumbent, output_dir, rung_index, **_kwargs):
        evaluated.append(challenger.submission.submission_id)
        return {
            "timestamp": "2026-05-24T00:00:00Z",
            "rung_index": rung_index,
            "challenger": {"submission_id": challenger.submission.submission_id},
            "incumbent": {"submission_id": incumbent.submission.submission_id},
            "gate": {"passed": False, "challenger_points": 1.0},
            "adaptive_gate": None,
            "confirmation": None,
            "promoted": False,
            "reason": "gate_failed",
            "result_path": str(Path(output_dir) / "result.json"),
        }

    monkeypatch.setattr("hex6.eval.ladder.evaluate_ladder_candidate", fake_evaluate_ladder_candidate)

    summary = run_ladder(
        config=config,
        config_path="configs/colab_ladder.toml",
        manifest_path=manifest_path,
        output_dir=tmp_path / "out",
        state_path=state_path,
        ledger_path=tmp_path / "strength_ledger.jsonl",
        resume=True,
    )

    assert evaluated == ["slot_02"]
    assert summary["processed_submission_ids"] == ["slot_01", "slot_02"]
    assert summary["remaining_submission_ids"] == []


def test_run_ladder_rejects_manifest_above_submission_cap(tmp_path: Path) -> None:
    config = load_config("configs/colab_ladder.toml")
    manifest_path = tmp_path / "ladder.toml"
    lines = [
        "[champion]",
        'submission_id = "champion"',
        'name = "Champion"',
        'kind = "baseline"',
        "",
    ]
    for index in range(9):
        lines.extend(
            [
                "[[submissions]]",
                f'submission_id = "slot_{index:02d}"',
                f'name = "Slot {index:02d}"',
                'kind = "baseline"',
                "",
            ]
        )
    manifest_path.write_text("\n".join(lines), encoding="ascii")

    try:
        run_ladder(
            config=config,
            config_path="configs/colab_ladder.toml",
            manifest_path=manifest_path,
            output_dir=tmp_path / "out",
            state_path=tmp_path / "state.json",
            ledger_path=tmp_path / "strength_ledger.jsonl",
            resume=False,
        )
    except ValueError as exc:
        assert "submission cap" in str(exc)
    else:
        raise AssertionError("expected ladder manifest larger than 8 submissions to be rejected")
