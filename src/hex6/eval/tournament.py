"""Round-robin tournament helpers for Hex6 agents."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from glob import glob
from itertools import combinations
from pathlib import Path
import json
from typing import Callable, Iterable

from hex6.config import AppConfig, load_config
from hex6.eval.arena import (
    AgentSpec,
    build_baseline_agent,
    build_checkpoint_agent,
    build_random_agent,
    run_arena,
)
from hex6.search.model_guided import load_checkpoint_metadata


@dataclass(frozen=True)
class TournamentParticipant:
    name: str
    kind: str
    agent: AgentSpec
    checkpoint_path: str | None = None
    config_path: str | None = None


TournamentProgressCallback = Callable[[dict[str, object]], None]


def discover_checkpoints(pattern: str, *, max_checkpoints: int) -> list[Path]:
    seen: set[str] = set()
    paths: list[Path] = []
    for raw in glob(pattern, recursive=True):
        resolved = Path(raw).resolve()
        if not resolved.is_file():
            continue
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        paths.append(resolved)

    paths.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    if max_checkpoints > 0:
        return paths[:max_checkpoints]
    return paths


def build_checkpoint_participant(
    checkpoint_path: str | Path,
    *,
    fallback_config_path: str | Path,
    display_name: str | None = None,
) -> TournamentParticipant:
    checkpoint = Path(checkpoint_path).resolve()
    config_path = resolved_checkpoint_config_path(checkpoint, fallback_config_path=fallback_config_path)
    checkpoint_config = load_config(config_path)
    checkpoint_agent = build_checkpoint_agent(checkpoint, checkpoint_config)

    wrapped_agent = AgentSpec(
        name=display_name or checkpoint.stem,
        kind="model_guided",
        choose_turn=lambda state, _arena_config, agent=checkpoint_agent, config=checkpoint_config: agent.choose_turn(
            state, config
        ),
    )
    return TournamentParticipant(
        name=wrapped_agent.name,
        kind=wrapped_agent.kind,
        agent=wrapped_agent,
        checkpoint_path=str(checkpoint),
        config_path=config_path,
    )


def build_participants(
    *,
    base_config_path: str | Path,
    include_baseline: bool,
    include_random: bool,
    random_seed: int,
    checkpoint_paths: Iterable[str | Path],
) -> tuple[TournamentParticipant, ...]:
    participants: list[TournamentParticipant] = []
    used_names: set[str] = set()

    if include_baseline:
        baseline = build_baseline_agent()
        participants.append(
            TournamentParticipant(
                name=baseline.name,
                kind=baseline.kind,
                agent=baseline,
            )
        )
        used_names.add(baseline.name)

    if include_random:
        random_agent = build_random_agent(seed=random_seed, name=f"random_seed_{random_seed}")
        participants.append(
            TournamentParticipant(
                name=random_agent.name,
                kind=random_agent.kind,
                agent=random_agent,
            )
        )
        used_names.add(random_agent.name)

    for checkpoint_path in checkpoint_paths:
        checkpoint = Path(checkpoint_path).resolve()
        proposed = checkpoint.parent.name + "_" + checkpoint.stem
        participant_name = unique_name(proposed, used_names)
        used_names.add(participant_name)
        participants.append(
            build_checkpoint_participant(
                checkpoint,
                fallback_config_path=base_config_path,
                display_name=participant_name,
            )
        )

    return tuple(participants)


def run_round_robin_tournament(
    *,
    participants: tuple[TournamentParticipant, ...],
    config: AppConfig,
    games_per_match: int,
    output_dir: str | Path,
    max_game_plies: int | None = None,
    progress_callback: TournamentProgressCallback | None = None,
) -> dict[str, object]:
    if len(participants) < 2:
        raise ValueError("at least two participants are required")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    matches_path = output_path / "matches"
    matches_path.mkdir(parents=True, exist_ok=True)

    evaluation = config.evaluation
    arena_config = replace(
        config,
        evaluation=replace(
            evaluation,
            max_game_plies=max_game_plies if max_game_plies is not None else evaluation.max_game_plies,
            record_game_history=True,
        ),
    )

    scoreboard: dict[str, dict[str, object]] = {
        participant.name: {
            "name": participant.name,
            "kind": participant.kind,
            "points": 0.0,
            "games": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "win_rate": 0.0,
            "checkpoint_path": participant.checkpoint_path,
            "config_path": participant.config_path,
        }
        for participant in participants
    }

    matches: list[dict[str, object]] = []
    total_matches = len(participants) * (len(participants) - 1) // 2
    for match_index, (participant_a, participant_b) in enumerate(combinations(participants, 2), start=1):
        summary = run_arena(
            agent_a=participant_a.agent,
            agent_b=participant_b.agent,
            config=arena_config,
            games=games_per_match,
        )
        game_history = summary.get("game_history", [])
        plies = [entry["plies"] for entry in game_history if isinstance(entry.get("plies"), int)]
        average_plies = round(sum(plies) / len(plies), 2) if plies else None

        record = {
            "timestamp": summary["timestamp"],
            "agent_a": participant_a.name,
            "agent_b": participant_b.name,
            "games": summary["games"],
            "wins_a": summary["wins_a"],
            "wins_b": summary["wins_b"],
            "draws": summary["draws"],
            "score_a": summary["score_a"],
            "score_b": summary["score_b"],
            "win_rate_a": summary["win_rate_a"],
            "win_rate_b": summary["win_rate_b"],
            "avg_plies": average_plies,
            "arena": summary,
        }
        matches.append(record)

        match_filename = f"{participant_a.name}_vs_{participant_b.name}.json"
        (matches_path / match_filename).write_text(json.dumps(record, indent=2), encoding="ascii")

        update_scoreboard(
            scoreboard=scoreboard,
            name_a=participant_a.name,
            name_b=participant_b.name,
            summary=summary,
        )
        if progress_callback is not None:
            current_leader = sorted(
                scoreboard.values(),
                key=lambda entry: (entry["points"], entry["wins"], -entry["losses"]),
                reverse=True,
            )[0]["name"]
            progress_callback(
                {
                    "stage": "tournament",
                    "completed_matches": match_index,
                    "total_matches": total_matches,
                    "agent_a": participant_a.name,
                    "agent_b": participant_b.name,
                    "wins_a": summary["wins_a"],
                    "wins_b": summary["wins_b"],
                    "draws": summary["draws"],
                    "leader": current_leader,
                }
            )

    leaderboard = sorted(
        scoreboard.values(),
        key=lambda entry: (entry["points"], entry["wins"], -entry["losses"]),
        reverse=True,
    )

    summary = {
        "timestamp": utc_now(),
        "games_per_match": games_per_match,
        "max_game_plies": arena_config.evaluation.max_game_plies,
        "participants": [
            {
                "name": participant.name,
                "kind": participant.kind,
                "checkpoint_path": participant.checkpoint_path,
                "config_path": participant.config_path,
            }
            for participant in participants
        ],
        "matches": matches,
        "leaderboard": leaderboard,
        "leader": leaderboard[0]["name"] if leaderboard else None,
    }

    summary_path = output_path / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="ascii")
    history_path = append_tournament_history(output_path.parent / "history.json", summary)
    summary["summary_path"] = str(summary_path)
    summary["history_path"] = str(history_path)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="ascii")
    return summary


def update_scoreboard(
    *,
    scoreboard: dict[str, dict[str, object]],
    name_a: str,
    name_b: str,
    summary: dict[str, object],
) -> None:
    entry_a = scoreboard[name_a]
    entry_b = scoreboard[name_b]

    games = int(summary["games"])
    wins_a = int(summary["wins_a"])
    wins_b = int(summary["wins_b"])
    draws = int(summary["draws"])
    score_a = float(summary["score_a"])
    score_b = float(summary["score_b"])

    entry_a["games"] = int(entry_a["games"]) + games
    entry_b["games"] = int(entry_b["games"]) + games
    entry_a["wins"] = int(entry_a["wins"]) + wins_a
    entry_b["wins"] = int(entry_b["wins"]) + wins_b
    entry_a["losses"] = int(entry_a["losses"]) + wins_b
    entry_b["losses"] = int(entry_b["losses"]) + wins_a
    entry_a["draws"] = int(entry_a["draws"]) + draws
    entry_b["draws"] = int(entry_b["draws"]) + draws
    entry_a["points"] = round(float(entry_a["points"]) + score_a, 3)
    entry_b["points"] = round(float(entry_b["points"]) + score_b, 3)

    entry_a["win_rate"] = round(float(entry_a["points"]) / max(int(entry_a["games"]), 1), 3)
    entry_b["win_rate"] = round(float(entry_b["points"]) / max(int(entry_b["games"]), 1), 3)


def append_tournament_history(path: Path, summary: dict[str, object]) -> Path:
    existing: list[dict[str, object]]
    if path.exists():
        existing = json.loads(path.read_text(encoding="ascii"))
    else:
        existing = []

    existing.append(
        {
            "timestamp": summary["timestamp"],
            "games_per_match": summary["games_per_match"],
            "max_game_plies": summary["max_game_plies"],
            "leader": summary["leader"],
            "leaderboard": summary["leaderboard"],
        }
    )
    path.write_text(json.dumps(existing, indent=2), encoding="ascii")
    return path


def resolved_checkpoint_config_path(checkpoint_path: Path, *, fallback_config_path: str | Path) -> str:
    metadata = load_checkpoint_metadata(checkpoint_path)
    raw = metadata.get("config_path")
    if isinstance(raw, str) and raw.strip():
        parsed = Path(raw)
        if not parsed.is_absolute():
            parsed = (Path.cwd() / parsed).resolve()
        if parsed.exists():
            return str(parsed)
    return str(Path(fallback_config_path).resolve())


def unique_name(candidate: str, used_names: set[str]) -> str:
    if candidate not in used_names:
        return candidate
    index = 2
    while True:
        proposed = f"{candidate}_{index}"
        if proposed not in used_names:
            return proposed
        index += 1


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
