"""Arena evaluation helpers."""

from .arena import (
    AgentSpec,
    append_elo_history,
    build_baseline_agent,
    build_checkpoint_agent,
    build_random_agent,
    evaluate_checkpoint_against_baseline,
    evaluate_checkpoint_against_opponent,
    play_game,
    random_candidate_cells,
    run_arena,
    update_elo,
)
from .search_matrix import run_search_variant_matrix
from .tournament import (
    TournamentParticipant,
    build_participants,
    discover_checkpoints,
    evaluate_checkpoint_with_tournament_gate,
    run_round_robin_tournament,
)

__all__ = [
    "AgentSpec",
    "append_elo_history",
    "build_baseline_agent",
    "build_checkpoint_agent",
    "build_participants",
    "build_random_agent",
    "discover_checkpoints",
    "evaluate_checkpoint_with_tournament_gate",
    "evaluate_checkpoint_against_baseline",
    "evaluate_checkpoint_against_opponent",
    "play_game",
    "random_candidate_cells",
    "run_arena",
    "run_round_robin_tournament",
    "run_search_variant_matrix",
    "TournamentParticipant",
    "update_elo",
]
