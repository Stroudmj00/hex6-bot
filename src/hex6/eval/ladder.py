"""Resumable engine ladder helpers for Colab-run evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
import json
import tomllib
from typing import Callable

from hex6.config import AppConfig, load_config
from hex6.eval.arena import AgentSpec, build_baseline_agent, build_checkpoint_agent, build_evaluation_config, build_random_agent, run_arena


LadderProgressCallback = Callable[[dict[str, object]], None]


@dataclass(frozen=True)
class LadderSubmission:
    submission_id: str
    name: str
    kind: str
    config_path: str = ""
    checkpoint_path: str = ""
    notes: str = ""
    slot: int = 0
    random_seed: int = 0
    random_candidate_width: int = 24


@dataclass(frozen=True)
class LadderManifest:
    champion: LadderSubmission
    submissions: tuple[LadderSubmission, ...]
    source_path: str


@dataclass(frozen=True)
class ResolvedLadderAgent:
    submission: LadderSubmission
    agent: AgentSpec
    config_path: str | None
    checkpoint_path: str | None


def load_ladder_manifest(path: str | Path) -> LadderManifest:
    manifest_path = Path(path).resolve()
    with manifest_path.open("rb") as handle:
        data = tomllib.load(handle)
    champion = _submission_from_mapping(data.get("champion", {}), fallback_id="champion", default_name="champion")
    raw_submissions = data.get("submissions", [])
    submissions = tuple(
        _submission_from_mapping(
            entry,
            fallback_id=f"submission_{index:02d}",
            default_name=f"submission_{index:02d}",
        )
        for index, entry in enumerate(raw_submissions, start=1)
    )
    seen: set[str] = set()
    for submission in (champion, *submissions):
        if submission.submission_id in seen:
            raise ValueError(f"duplicate ladder submission_id: {submission.submission_id}")
        seen.add(submission.submission_id)
    return LadderManifest(
        champion=champion,
        submissions=submissions,
        source_path=str(manifest_path),
    )


def resolve_ladder_agent(
    submission: LadderSubmission,
    *,
    base_eval_config: AppConfig,
    reference_path: str | Path,
) -> ResolvedLadderAgent:
    config_path = None
    if submission.config_path.strip():
        config_path = str(_resolve_path(reference_path, submission.config_path, require_exists=True))
        submission_config = load_config(config_path)
    else:
        submission_config = base_eval_config
    play_config = _merge_play_config(base_eval_config, submission_config)

    kind = submission.kind.strip().lower()
    if kind == "baseline":
        agent = build_baseline_agent(play_config=play_config)
    elif kind == "random":
        agent = build_random_agent(
            seed=submission.random_seed,
            candidate_width=submission.random_candidate_width,
            name=submission.name,
            play_config=play_config,
        )
    elif kind == "checkpoint":
        if not submission.checkpoint_path.strip():
            raise ValueError(f"checkpoint submission {submission.submission_id} is missing checkpoint_path")
        checkpoint_path = str(_resolve_path(reference_path, submission.checkpoint_path, require_exists=True))
        agent = build_checkpoint_agent(checkpoint_path, play_config)
    else:
        raise ValueError(f"unsupported ladder submission kind: {submission.kind}")

    checkpoint_path = (
        str(_resolve_path(reference_path, submission.checkpoint_path, require_exists=True))
        if submission.checkpoint_path.strip()
        else None
    )
    return ResolvedLadderAgent(
        submission=submission,
        agent=replace(agent, name=submission.name, play_config=play_config),
        config_path=config_path,
        checkpoint_path=checkpoint_path,
    )


def run_ladder_gate(
    *,
    challenger: ResolvedLadderAgent,
    incumbent: ResolvedLadderAgent,
    config: AppConfig,
    output_dir: str | Path,
    games: int,
    required_points: float,
    rung_index: int,
    phase: str,
    progress_callback: LadderProgressCallback | None = None,
) -> dict[str, object]:
    if config.ladder.gate_balanced_sides and games % 2 != 0:
        raise ValueError("ladder gate requires an even game count when balanced sides are enabled")
    if not config.ladder.gate_empty_board_only:
        raise ValueError("ladder gate currently supports empty-board evaluation only")

    phase_output = Path(output_dir)
    phase_output.mkdir(parents=True, exist_ok=True)
    summary = run_arena(
        agent_a=challenger.agent,
        agent_b=incumbent.agent,
        config=config,
        games=games,
        opening_suite=None,
        progress_callback=_ladder_progress_wrapper(
            progress_callback,
            rung_index=rung_index,
            phase=phase,
            challenger=challenger.submission,
        ),
    )
    summary_path = phase_output / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="ascii")

    challenger_points = float(summary["score_a"])
    incumbent_points = float(summary["score_b"])
    challenger_as_x, challenger_as_o = _side_counts(summary, games)
    balanced = challenger_as_x == challenger_as_o if config.ladder.gate_balanced_sides else True
    gate_summary = {
        "phase": phase,
        "rung_index": rung_index,
        "games": games,
        "required_points": required_points,
        "challenger_points": challenger_points,
        "incumbent_points": incumbent_points,
        "challenger_wins": summary["wins_a"],
        "challenger_losses": summary["wins_b"],
        "draws": summary["draws"],
        "draw_rate": summary["draw_rate"],
        "challenger_as_x": challenger_as_x,
        "challenger_as_o": challenger_as_o,
        "balanced_sides": balanced,
        "empty_board_only": True,
        "passed": balanced and challenger_points >= required_points,
        "summary_path": str(summary_path),
    }
    summary_path.write_text(json.dumps({**summary, "gate": gate_summary}, indent=2), encoding="ascii")
    return gate_summary


def evaluate_ladder_candidate(
    *,
    challenger: ResolvedLadderAgent,
    incumbent: ResolvedLadderAgent,
    config: AppConfig,
    output_dir: str | Path,
    rung_index: int,
    progress_callback: LadderProgressCallback | None = None,
) -> dict[str, object]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    gate = run_ladder_gate(
        challenger=challenger,
        incumbent=incumbent,
        config=config,
        output_dir=output_path / "gate",
        games=config.ladder.gate_games,
        required_points=config.ladder.gate_required_points,
        rung_index=rung_index,
        phase="gate",
        progress_callback=progress_callback,
    )

    adaptive: dict[str, object] | None = None
    confirmation: dict[str, object] | None = None
    confirmation_challenger = challenger
    confirmation_incumbent = incumbent
    promoted = False
    reason = "gate_failed"

    if gate["passed"]:
        confirmation = run_ladder_gate(
            challenger=challenger,
            incumbent=incumbent,
            config=config,
            output_dir=output_path / "confirmation",
            games=config.ladder.confirmation_games,
            required_points=config.ladder.confirmation_required_points,
            rung_index=rung_index,
            phase="confirmation",
            progress_callback=progress_callback,
        )
        promoted = bool(confirmation["passed"])
        reason = "promoted" if promoted else "confirmation_failed"
    elif config.ladder.adaptive_enabled and gate["challenger_points"] >= config.ladder.adaptive_trigger_points:
        confirmation_challenger = _with_compute_bonus(challenger, config)
        confirmation_incumbent = _with_compute_bonus(incumbent, config)
        adaptive = run_ladder_gate(
            challenger=confirmation_challenger,
            incumbent=confirmation_incumbent,
            config=config,
            output_dir=output_path / "adaptive_gate",
            games=config.ladder.adaptive_games,
            required_points=config.ladder.adaptive_required_points,
            rung_index=rung_index,
            phase="adaptive_gate",
            progress_callback=progress_callback,
        )
        if adaptive["passed"]:
            confirmation = run_ladder_gate(
                challenger=confirmation_challenger,
                incumbent=confirmation_incumbent,
                config=config,
                output_dir=output_path / "confirmation",
                games=config.ladder.confirmation_games,
                required_points=config.ladder.confirmation_required_points,
                rung_index=rung_index,
                phase="confirmation",
                progress_callback=progress_callback,
            )
            promoted = bool(confirmation["passed"])
            reason = "promoted_after_adaptive" if promoted else "confirmation_failed"
        else:
            reason = "adaptive_failed"

    result = {
        "timestamp": utc_now(),
        "rung_index": rung_index,
        "challenger": _submission_payload(challenger),
        "incumbent": _submission_payload(incumbent),
        "gate": gate,
        "adaptive_gate": adaptive,
        "confirmation": confirmation,
        "promoted": promoted,
        "reason": reason,
        "result_path": str(output_path / "result.json"),
    }
    Path(result["result_path"]).write_text(json.dumps(result, indent=2), encoding="ascii")
    return result


def append_strength_ledger(path: str | Path, entry: dict[str, object]) -> Path:
    ledger_path = Path(path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="ascii") as handle:
        handle.write(json.dumps(entry) + "\n")
    return ledger_path


def load_ladder_state(path: str | Path) -> dict[str, object]:
    state_path = Path(path)
    if not state_path.exists():
        return {}
    return json.loads(state_path.read_text(encoding="ascii"))


def write_ladder_state(path: str | Path, payload: dict[str, object]) -> Path:
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, indent=2), encoding="ascii")
    return state_path


def run_ladder(
    *,
    config: AppConfig,
    config_path: str | Path,
    manifest_path: str | Path,
    output_dir: str | Path,
    state_path: str | Path,
    ledger_path: str | Path,
    resume: bool = True,
    max_submissions: int | None = None,
    progress_callback: LadderProgressCallback | None = None,
) -> dict[str, object]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    manifest = load_ladder_manifest(manifest_path)
    eval_config = build_evaluation_config(config)
    if len(manifest.submissions) > config.ladder.max_submissions_per_rung:
        raise ValueError(
            "ladder manifest exceeds configured submission cap: "
            f"{len(manifest.submissions)} > {config.ladder.max_submissions_per_rung}"
        )
    existing = load_ladder_state(state_path) if resume else {}
    processed = set(existing.get("processed_submission_ids", []))
    results: list[dict[str, object]] = list(existing.get("results", []))
    promoted_submission_ids: list[str] = list(existing.get("promoted_submission_ids", []))

    champion = _submission_from_mapping(
        existing.get("champion", asdict(manifest.champion)),
        fallback_id=manifest.champion.submission_id,
        default_name=manifest.champion.name,
    )
    pending = [
        submission
        for submission in manifest.submissions
        if submission.submission_id not in processed and submission.submission_id != champion.submission_id
    ]
    submission_cap = config.ladder.max_submissions_per_rung if max_submissions is None else max_submissions
    if submission_cap is not None and submission_cap > 0:
        pending = pending[:submission_cap]

    if progress_callback is not None:
        progress_callback(
            {
                "stage": "ladder_starting",
                "manifest_path": manifest.source_path,
                "champion_submission_id": champion.submission_id,
                "pending_submissions": len(pending),
            }
        )

    for submission in pending:
        rung_index = len(results) + 1
        challenger = resolve_ladder_agent(
            submission,
            base_eval_config=eval_config,
            reference_path=manifest.source_path,
        )
        incumbent = resolve_ladder_agent(
            champion,
            base_eval_config=eval_config,
            reference_path=manifest.source_path,
        )
        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "ladder_candidate_start",
                    "rung_index": rung_index,
                    "submission_id": submission.submission_id,
                    "submission_name": submission.name,
                    "champion_submission_id": champion.submission_id,
                }
            )
        result = evaluate_ladder_candidate(
            challenger=challenger,
            incumbent=incumbent,
            config=eval_config,
            output_dir=output_path / f"rung_{rung_index:03d}_{submission.submission_id}",
            rung_index=rung_index,
            progress_callback=progress_callback,
        )
        results.append(result)
        processed.add(submission.submission_id)
        if result["promoted"]:
            champion = submission
            promoted_submission_ids.append(submission.submission_id)
        append_strength_ledger(ledger_path, result)
        state_payload = _ladder_state_payload(
            manifest=manifest,
            champion=champion,
            processed_submission_ids=processed,
            promoted_submission_ids=promoted_submission_ids,
            results=results,
            state_path=state_path,
            ledger_path=ledger_path,
            output_dir=output_path,
        )
        write_ladder_state(state_path, state_payload)
        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "ladder_candidate_complete",
                    "rung_index": rung_index,
                    "submission_id": submission.submission_id,
                    "promoted": result["promoted"],
                    "reason": result["reason"],
                    "champion_submission_id": champion.submission_id,
                }
            )

    summary = _ladder_state_payload(
        manifest=manifest,
        champion=champion,
        processed_submission_ids=processed,
        promoted_submission_ids=promoted_submission_ids,
        results=results,
        state_path=state_path,
        ledger_path=ledger_path,
        output_dir=output_path,
    )
    summary_path = output_path / "ladder_summary.json"
    summary["summary_path"] = str(summary_path)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="ascii")
    write_ladder_state(state_path, summary)
    if progress_callback is not None:
        progress_callback(
            {
                "stage": "ladder_complete",
                "champion_submission_id": champion.submission_id,
                "processed_submissions": len(processed),
                "remaining_submissions": len(summary["remaining_submission_ids"]),
                "summary_path": str(summary_path),
            }
        )
    return summary


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _submission_from_mapping(
    data: dict[str, object],
    *,
    fallback_id: str,
    default_name: str,
) -> LadderSubmission:
    if not isinstance(data, dict):
        raise ValueError("ladder submission entries must be mappings")
    name = str(data.get("name", default_name)).strip() or default_name
    submission_id = str(data.get("submission_id", fallback_id)).strip() or fallback_id
    return LadderSubmission(
        submission_id=submission_id,
        name=name,
        kind=str(data.get("kind", "checkpoint")),
        config_path=str(data.get("config_path", "")),
        checkpoint_path=str(data.get("checkpoint_path", "")),
        notes=str(data.get("notes", "")),
        slot=int(data.get("slot", 0) or 0),
        random_seed=int(data.get("random_seed", 0) or 0),
        random_candidate_width=int(data.get("random_candidate_width", 24) or 24),
    )


def _submission_payload(agent: ResolvedLadderAgent) -> dict[str, object]:
    payload = asdict(agent.submission)
    payload["resolved_config_path"] = agent.config_path
    payload["resolved_checkpoint_path"] = agent.checkpoint_path
    payload["agent_kind"] = agent.agent.kind
    return payload


def _merge_play_config(base_eval_config: AppConfig, submission_config: AppConfig) -> AppConfig:
    return replace(
        submission_config,
        game=base_eval_config.game,
        evaluation=base_eval_config.evaluation,
        integration=base_eval_config.integration,
        ladder=base_eval_config.ladder,
    )


def _with_compute_bonus(agent: ResolvedLadderAgent, config: AppConfig) -> ResolvedLadderAgent:
    play_config = agent.agent.play_config
    if play_config is None:
        return agent
    boosted = replace(
        play_config,
        search=replace(
            play_config.search,
            root_simulations=max(1, play_config.search.root_simulations + config.ladder.adaptive_root_simulation_bonus),
            parallel_expansions_per_root=max(
                1,
                play_config.search.parallel_expansions_per_root + config.ladder.adaptive_parallel_expansion_bonus,
            ),
        ),
    )
    return replace(
        agent,
        agent=replace(agent.agent, play_config=boosted),
    )


def _side_counts(summary: dict[str, object], games: int) -> tuple[int, int]:
    history = summary.get("game_history")
    if isinstance(history, list):
        challenger_name = summary["agent_a"]["name"]
        as_x = 0
        as_o = 0
        for entry in history:
            if not isinstance(entry, dict):
                continue
            if entry.get("x_agent") == challenger_name:
                as_x += 1
            if entry.get("o_agent") == challenger_name:
                as_o += 1
        return as_x, as_o
    as_x = (games + 1) // 2
    as_o = games // 2
    return as_x, as_o


def _resolve_path(reference_path: str | Path, raw_path: str | Path, *, require_exists: bool) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        resolved = path.resolve()
    else:
        resolved = (Path(reference_path).resolve().parent / path).resolve()
    if require_exists and not resolved.exists():
        raise ValueError(f"path does not exist: {resolved}")
    return resolved


def _ladder_progress_wrapper(
    callback: LadderProgressCallback | None,
    *,
    rung_index: int,
    phase: str,
    challenger: LadderSubmission,
) -> Callable[[dict[str, object]], None] | None:
    if callback is None:
        return None

    def wrapped(payload: dict[str, object]) -> None:
        callback(
            {
                "stage": payload.get("stage", "evaluation"),
                "ladder_phase": phase,
                "rung_index": rung_index,
                "submission_id": challenger.submission_id,
                "submission_name": challenger.name,
                **payload,
            }
        )

    return wrapped


def _ladder_state_payload(
    *,
    manifest: LadderManifest,
    champion: LadderSubmission,
    processed_submission_ids: set[str],
    promoted_submission_ids: list[str],
    results: list[dict[str, object]],
    state_path: str | Path,
    ledger_path: str | Path,
    output_dir: Path,
) -> dict[str, object]:
    remaining_submission_ids = [
        submission.submission_id
        for submission in manifest.submissions
        if submission.submission_id not in processed_submission_ids and submission.submission_id != champion.submission_id
    ]
    return {
        "generated_at": utc_now(),
        "manifest_path": manifest.source_path,
        "champion": asdict(champion),
        "processed_submission_ids": sorted(processed_submission_ids),
        "promoted_submission_ids": promoted_submission_ids,
        "remaining_submission_ids": remaining_submission_ids,
        "results": results,
        "state_path": str(Path(state_path).resolve()),
        "ledger_path": str(Path(ledger_path).resolve()),
        "output_dir": str(output_dir.resolve()),
    }
