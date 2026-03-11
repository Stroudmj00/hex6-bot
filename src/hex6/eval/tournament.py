"""Round-robin tournament helpers for Hex6 agents."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from glob import glob
from itertools import combinations
from pathlib import Path
import json
from typing import Callable, Iterable

from hex6.config import AppConfig
from hex6.eval.arena import (
    AgentSpec,
    build_baseline_agent,
    build_checkpoint_agent,
    build_checkpoint_load_config,
    build_evaluation_config,
    build_random_agent,
    resolve_checkpoint_config_path,
    run_arena,
)
from hex6.eval.openings import OpeningScenario, load_opening_suite


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
    if max_checkpoints == 0:
        return []
    if max_checkpoints > 0:
        return paths[:max_checkpoints]
    return paths


def build_checkpoint_participant(
    checkpoint_path: str | Path,
    *,
    agent_config: AppConfig,
    fallback_config_path: str | Path,
    display_name: str | None = None,
) -> TournamentParticipant:
    checkpoint = Path(checkpoint_path).resolve()
    config_path = resolve_checkpoint_config_path(checkpoint, fallback_config_path=fallback_config_path)
    checkpoint_agent = build_checkpoint_agent(
        checkpoint,
        build_checkpoint_load_config(
            checkpoint,
            agent_config,
            fallback_config_path=fallback_config_path,
        ),
    )

    wrapped_agent = AgentSpec(
        name=display_name or checkpoint.stem,
        kind=checkpoint_agent.kind,
        choose_turn=lambda state, arena_config, agent=checkpoint_agent: agent.choose_turn(
            state, arena_config
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
    agent_config: AppConfig,
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
                agent_config=agent_config,
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
    opening_suite: list[OpeningScenario] | None = None,
    progress_callback: TournamentProgressCallback | None = None,
) -> dict[str, object]:
    if len(participants) < 2:
        raise ValueError("at least two participants are required")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    matches_path = output_path / "matches"
    matches_path.mkdir(parents=True, exist_ok=True)

    eval_config = build_evaluation_config(config)
    evaluation = config.evaluation
    arena_config = replace(
        eval_config,
        evaluation=replace(
            eval_config.evaluation,
            max_game_plies=max_game_plies if max_game_plies is not None else evaluation.max_game_plies,
            record_game_history=True,
        ),
    )

    effective_games_per_match = max(1, games_per_match)
    if opening_suite and effective_games_per_match < len(opening_suite):
        effective_games_per_match = len(opening_suite)

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
            games=effective_games_per_match,
            opening_suite=opening_suite,
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
            "draws_by_ply_cap": summary["draws_by_ply_cap"],
            "draws_by_board_exhausted": summary["draws_by_board_exhausted"],
            "draws_non_ply_cap": summary["draws_non_ply_cap"],
            "draw_rate": summary["draw_rate"],
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
                    "draws_by_ply_cap": summary["draws_by_ply_cap"],
                    "draws_by_board_exhausted": summary["draws_by_board_exhausted"],
                    "leader": current_leader,
                }
            )

    leaderboard = sorted(
        scoreboard.values(),
        key=lambda entry: (entry["points"], entry["wins"], -entry["losses"]),
        reverse=True,
    )

    total_games = sum(int(match["games"]) for match in matches)
    total_draws = sum(int(match["draws"]) for match in matches)
    total_draws_by_ply_cap = sum(int(match["draws_by_ply_cap"]) for match in matches)
    total_draws_by_board_exhausted = sum(int(match["draws_by_board_exhausted"]) for match in matches)
    total_decisive_games = max(0, total_games - total_draws)

    summary = {
        "timestamp": utc_now(),
        "requested_games_per_match": games_per_match,
        "games_per_match": effective_games_per_match,
        "max_game_plies": arena_config.evaluation.max_game_plies,
        "board_mode": arena_config.game.board_mode,
        "board_width": arena_config.game.board_width,
        "board_height": arena_config.game.board_height,
        "opening_suite_size": len(opening_suite) if opening_suite else 0,
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
        "total_games": total_games,
        "total_draws": total_draws,
        "total_draws_by_ply_cap": total_draws_by_ply_cap,
        "total_draws_by_board_exhausted": total_draws_by_board_exhausted,
        "total_decisive_games": total_decisive_games,
        "draw_rate": round(total_draws / max(total_games, 1), 3),
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


def evaluate_checkpoint_with_tournament_gate(
    checkpoint_path: str | Path,
    config: AppConfig,
    *,
    config_path: str | Path,
    output_dir: str | Path,
    extra_checkpoint_paths: Iterable[str | Path] = (),
    include_baseline: bool = True,
    include_random: bool = False,
    random_seed: int = 7,
    progress_callback: TournamentProgressCallback | None = None,
) -> dict[str, object]:
    eval_config = build_evaluation_config(config)
    checkpoint = Path(checkpoint_path).resolve()
    checkpoint_key = normalized_path_string(checkpoint)
    extras: list[Path] = []
    for extra in extra_checkpoint_paths:
        resolved = Path(extra).resolve()
        if resolved == checkpoint or not resolved.exists():
            continue
        extras.append(resolved)

    opening_suite = None
    if eval_config.evaluation.post_train_opening_suite.strip():
        opening_suite = load_opening_suite(
            resolve_path_relative_to_config(config_path, eval_config.evaluation.post_train_opening_suite),
            eval_config,
        )

    participants = build_participants(
        agent_config=eval_config,
        base_config_path=config_path,
        include_baseline=include_baseline,
        include_random=include_random,
        random_seed=random_seed,
        checkpoint_paths=[*extras, checkpoint],
    )
    summary = run_round_robin_tournament(
        participants=participants,
        config=eval_config,
        games_per_match=max(eval_config.evaluation.arena_games, 1),
        output_dir=Path(output_dir) / "tournament",
        max_game_plies=eval_config.evaluation.post_train_max_game_plies,
        opening_suite=opening_suite,
        progress_callback=progress_callback,
    )

    leaderboard = list(summary["leaderboard"])
    checkpoint_entry = next(
        (
            entry
            for entry in leaderboard
            if isinstance(entry.get("checkpoint_path"), str)
            and normalized_path_string(entry["checkpoint_path"]) == checkpoint_key
        ),
        None,
    )
    if checkpoint_entry is None:
        raise ValueError(f"checkpoint {checkpoint} was not found in tournament leaderboard")
    checkpoint_name = str(checkpoint_entry["name"])
    checkpoint_rank = next(index for index, entry in enumerate(leaderboard, start=1) if entry["name"] == checkpoint_name)
    return {
        "kind": "tournament",
        "leader": summary["leader"],
        "participant_count": len(summary["participants"]),
        "games_per_match": summary["games_per_match"],
        "max_game_plies": summary["max_game_plies"],
        "board_width": summary.get("board_width"),
        "board_height": summary.get("board_height"),
        "opening_suite_size": summary["opening_suite_size"],
        "draw_rate": summary["draw_rate"],
        "total_draws": summary["total_draws"],
        "total_draws_by_ply_cap": summary["total_draws_by_ply_cap"],
        "total_draws_by_board_exhausted": summary["total_draws_by_board_exhausted"],
        "total_decisive_games": summary["total_decisive_games"],
        "checkpoint_name": checkpoint_name,
        "checkpoint_rank": checkpoint_rank,
        "checkpoint_points": checkpoint_entry["points"],
        "checkpoint_win_rate": checkpoint_entry["win_rate"],
        "checkpoint_wins": checkpoint_entry["wins"],
        "checkpoint_losses": checkpoint_entry["losses"],
        "checkpoint_draws": checkpoint_entry["draws"],
        "summary_path": summary["summary_path"],
        "history_path": summary["history_path"],
    }


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
            "board_mode": summary.get("board_mode"),
            "board_width": summary.get("board_width"),
            "board_height": summary.get("board_height"),
            "games_per_match": summary["games_per_match"],
            "max_game_plies": summary["max_game_plies"],
            "leader": summary["leader"],
            "leaderboard": summary["leaderboard"],
        }
    )
    path.write_text(json.dumps(existing, indent=2), encoding="ascii")
    return path

def resolve_path_relative_to_config(config_path: str | Path, raw_path: str | Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        if not path.exists():
            raise ValueError(f"path does not exist: {path}")
        return path

    config_relative = (Path(config_path).resolve().parent / path).resolve()
    repo_relative = (Path.cwd() / path).resolve()

    if config_relative.exists() and repo_relative.exists() and config_relative != repo_relative:
        raise ValueError(
            "ambiguous relative path "
            f"{raw_path!s}; both {config_relative} and {repo_relative} exist"
        )
    if config_relative.exists():
        return config_relative
    if repo_relative.exists():
        return repo_relative
    raise ValueError(
        "could not resolve path "
        f"{raw_path!s}; tried {config_relative} and {repo_relative}"
    )


def normalized_path_string(value: str | Path) -> str:
    return str(Path(value).resolve()).lower()


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
