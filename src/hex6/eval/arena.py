"""Arena evaluation and Elo tracking for Hex6 agents."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Callable

from hex6.config import AppConfig
from hex6.game import GameState, Player
from hex6.search import BaselineTurnSearch, ModelGuidedTurnSearch


ArenaProgressCallback = Callable[[dict[str, object]], None]


@dataclass(frozen=True)
class AgentSpec:
    name: str
    kind: str
    choose_turn: Callable[[GameState, AppConfig], object]


@dataclass(frozen=True)
class ArenaGameResult:
    game_index: int
    x_agent: str
    o_agent: str
    winner: Player | None
    plies: int
    score_a: float
    score_b: float
    a_rating: float
    b_rating: float


def evaluate_checkpoint_against_baseline(
    checkpoint_path: str | Path,
    config: AppConfig,
    *,
    output_dir: str | Path,
    progress_callback: ArenaProgressCallback | None = None,
) -> dict[str, object]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    model_agent = build_checkpoint_agent(checkpoint_path, config)
    baseline_agent = build_baseline_agent()
    summary = run_arena(
        agent_a=model_agent,
        agent_b=baseline_agent,
        config=config,
        games=config.evaluation.arena_games,
        progress_callback=progress_callback,
    )

    arena_path = output_path / "arena.json"
    arena_path.write_text(json.dumps(summary, indent=2), encoding="ascii")
    history_path = append_elo_history(output_path / "elo_history.json", summary)
    summary["arena_path"] = str(arena_path)
    summary["elo_history_path"] = str(history_path)
    arena_path.write_text(json.dumps(summary, indent=2), encoding="ascii")
    return summary


def build_baseline_agent() -> AgentSpec:
    search = BaselineTurnSearch()
    return AgentSpec(
        name="baseline",
        kind="heuristic",
        choose_turn=search.choose_turn,
    )


def build_checkpoint_agent(checkpoint_path: str | Path, config: AppConfig) -> AgentSpec:
    search = ModelGuidedTurnSearch.from_checkpoint(checkpoint_path, config)
    return AgentSpec(
        name=Path(checkpoint_path).stem,
        kind="model_guided",
        choose_turn=search.choose_turn,
    )


def run_arena(
    *,
    agent_a: AgentSpec,
    agent_b: AgentSpec,
    config: AppConfig,
    games: int,
    progress_callback: ArenaProgressCallback | None = None,
) -> dict[str, object]:
    rating_a = config.evaluation.initial_elo
    rating_b = config.evaluation.initial_elo
    results: list[ArenaGameResult] = []
    wins_a = 0
    wins_b = 0
    draws = 0

    for game_index in range(games):
        agents_by_player = (
            {"x": agent_a, "o": agent_b}
            if game_index % 2 == 0
            else {"x": agent_b, "o": agent_a}
        )
        winner, plies = play_game(agents_by_player, config)
        score_a, score_b = score_agents(agent_a, agent_b, agents_by_player, winner)
        rating_a, rating_b = update_elo(
            rating_a,
            rating_b,
            score_a,
            config.evaluation.k_factor,
        )

        if score_a == 1.0:
            wins_a += 1
        elif score_b == 1.0:
            wins_b += 1
        else:
            draws += 1

        result = ArenaGameResult(
            game_index=game_index + 1,
            x_agent=agents_by_player["x"].name,
            o_agent=agents_by_player["o"].name,
            winner=winner,
            plies=plies,
            score_a=score_a,
            score_b=score_b,
            a_rating=round(rating_a, 2),
            b_rating=round(rating_b, 2),
        )
        results.append(result)
        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "evaluation",
                    "completed_games": game_index + 1,
                    "total_games": games,
                    "wins_a": wins_a,
                    "wins_b": wins_b,
                    "draws": draws,
                    "current_elo_a": result.a_rating,
                    "current_elo_b": result.b_rating,
                }
            )

    score_total_a = wins_a + draws * 0.5
    score_total_b = wins_b + draws * 0.5
    summary: dict[str, object] = {
        "timestamp": utc_now(),
        "agent_a": {"name": agent_a.name, "kind": agent_a.kind},
        "agent_b": {"name": agent_b.name, "kind": agent_b.kind},
        "games": games,
        "wins_a": wins_a,
        "wins_b": wins_b,
        "draws": draws,
        "score_a": score_total_a,
        "score_b": score_total_b,
        "final_elo_a": round(rating_a, 2),
        "final_elo_b": round(rating_b, 2),
        "elo_delta_a": round(rating_a - config.evaluation.initial_elo, 2),
        "elo_delta_b": round(rating_b - config.evaluation.initial_elo, 2),
        "win_rate_a": round(score_total_a / max(games, 1), 3),
        "win_rate_b": round(score_total_b / max(games, 1), 3),
    }
    if config.evaluation.record_game_history:
        summary["game_history"] = [asdict(result) for result in results]
    return summary


def play_game(agents_by_player: dict[Player, AgentSpec], config: AppConfig) -> tuple[Player | None, int]:
    state = GameState.initial(config.game)
    while not state.is_terminal and state.ply_count < config.evaluation.max_game_plies:
        agent = agents_by_player[state.to_play]
        turn = agent.choose_turn(state, config)
        for cell in turn.cells:
            state = state.apply_placement(cell, config.game)
            if state.is_terminal:
                break
    return state.winner, state.ply_count


def score_agents(
    agent_a: AgentSpec,
    agent_b: AgentSpec,
    agents_by_player: dict[Player, AgentSpec],
    winner: Player | None,
) -> tuple[float, float]:
    if winner is None:
        return 0.5, 0.5
    winner_agent = agents_by_player[winner]
    if winner_agent == agent_a:
        return 1.0, 0.0
    return 0.0, 1.0


def update_elo(rating_a: float, rating_b: float, score_a: float, k_factor: float) -> tuple[float, float]:
    expected_a = 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))
    expected_b = 1.0 - expected_a
    score_b = 1.0 - score_a
    next_a = rating_a + k_factor * (score_a - expected_a)
    next_b = rating_b + k_factor * (score_b - expected_b)
    return next_a, next_b


def append_elo_history(path: Path, summary: dict[str, object]) -> Path:
    existing: list[dict[str, object]]
    if path.exists():
        existing = json.loads(path.read_text(encoding="ascii"))
    else:
        existing = []

    existing.append(
        {
            "timestamp": summary["timestamp"],
            "agent_a": summary["agent_a"],
            "agent_b": summary["agent_b"],
            "games": summary["games"],
            "win_rate_a": summary["win_rate_a"],
            "final_elo_a": summary["final_elo_a"],
            "elo_delta_a": summary["elo_delta_a"],
        }
    )
    path.write_text(json.dumps(existing, indent=2), encoding="ascii")
    return path


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
