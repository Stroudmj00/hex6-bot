"""Typed configuration schema for the Hex6 research scaffold."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import tomllib
from typing import Any


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    phase: str


@dataclass(frozen=True)
class RuntimeConfig:
    python_version: str
    preferred_device: str
    allow_cpu_fallback: bool
    cpu_threads: int
    interop_threads: int
    enable_tf32: bool
    cudnn_benchmark: bool
    record_resource_usage: bool
    resource_poll_seconds: float


@dataclass(frozen=True)
class GameConfig:
    board_mode: str
    board_width: int
    board_height: int
    board_center_q: int
    board_center_r: int
    coordinate_system: str
    players: tuple[str, str]
    win_length: int
    opening_placements: int
    turn_placements: int
    contiguous_lines_only: bool

    def __post_init__(self) -> None:
        if self.board_mode == "sparse_bounded" and (self.board_width <= 0 or self.board_height <= 0):
            raise ValueError(
                "bounded boards require positive board_width and board_height values"
            )

    @lru_cache(maxsize=None)
    def bounds(self) -> tuple[int, int, int, int] | None:
        if self.board_mode != "sparse_bounded":
            return None
        min_q = self.board_center_q - self.board_width // 2
        min_r = self.board_center_r - self.board_height // 2
        max_q = min_q + self.board_width - 1
        max_r = min_r + self.board_height - 1
        return min_q, max_q, min_r, max_r

    def is_in_bounds(self, cell: tuple[int, int]) -> bool:
        bounds = self.bounds()
        if bounds is None:
            return True
        min_q, max_q, min_r, max_r = bounds
        q, r = cell
        return min_q <= q <= max_q and min_r <= r <= max_r

    def opening_cell(self) -> tuple[int, int]:
        return self.board_center_q, self.board_center_r

    def is_bounded(self) -> bool:
        return self.bounds() is not None


@dataclass(frozen=True)
class PrototypeConfig:
    analysis_margin: int
    outer_search_margin: int
    prune_globally_dead_cells: bool
    allow_long_range_islands: bool
    first_stone_candidate_limit: int
    second_stone_candidate_limit: int
    frontier_distance: int
    island_min_distance: int
    island_max_distance: int
    min_open_windows_for_island: int


@dataclass(frozen=True)
class SearchConfig:
    algorithm: str
    factorize_two_stone_actions: bool
    use_progressive_widening: bool
    use_transposition_table: bool
    root_simulations: int
    parallel_expansions_per_root: int
    tactical_solver: str
    shallow_reply_width: int
    reply_depth: int
    puct_exploration: float
    dirichlet_alpha: float
    dirichlet_epsilon: float
    root_policy_mode: str = "visit_count"
    root_gumbel_scale: float = 1.0


@dataclass(frozen=True)
class TrainingConfig:
    bootstrap_strategy: str
    symmetry_augmentation: bool
    mixed_precision: bool
    self_play_workers: int
    data_loader_workers: int
    pin_memory: bool
    replay_buffer_size: int
    bootstrap_games: int
    max_game_plies: int
    batch_size: int
    epochs: int
    learning_rate: float
    policy_target: str
    bootstrap_opening_suite: str
    bootstrap_seeded_start_fraction: float
    self_play_temperature: float
    self_play_temperature_drop_ply: int
    self_play_temperature_after_drop: float
    reanalyse_fraction: float
    reanalyse_max_examples: int


@dataclass(frozen=True)
class ModelConfig:
    architecture: str
    board_crop_radius: int
    channels: int
    blocks: int


@dataclass(frozen=True)
class ScoringConfig:
    frontier: float
    friendly_open_window: float
    enemy_open_window: float
    friendly_alignment: float
    enemy_alignment: float
    intersection: float
    island: float
    space: float


@dataclass(frozen=True)
class HeuristicConfig:
    alignment_weights: tuple[float, ...]
    enemy_alignment_weights: tuple[float, ...]
    live_cell_weight: float
    candidate_score_weight: float
    terminal_score: float
    include_candidate_edge: bool


@dataclass(frozen=True)
class IntegrationConfig:
    status_backend: str
    github_repo: str
    github_branch: str
    github_base_branch: str
    status_path: str
    run_history_path: str
    watch_poll_seconds: float


@dataclass(frozen=True)
class EvaluationConfig:
    arena_games: int
    max_game_plies: int
    board_width_override: int
    board_height_override: int
    post_train_eval: str
    post_train_max_game_plies: int
    post_train_opening_suite: str
    promotion_games_per_match: int
    promotion_opening_suite: str
    promotion_include_baseline: bool
    promotion_require_candidate_rank_one: bool
    promotion_min_score_delta: float
    initial_elo: float
    k_factor: float
    model_policy_weight: float
    model_value_weight: float
    model_heuristic_weight: float
    record_game_history: bool


@dataclass(frozen=True)
class AppConfig:
    project: ProjectConfig
    runtime: RuntimeConfig
    game: GameConfig
    prototype: PrototypeConfig
    search: SearchConfig
    training: TrainingConfig
    model: ModelConfig
    scoring: ScoringConfig
    heuristic: HeuristicConfig
    integration: IntegrationConfig
    evaluation: EvaluationConfig

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "AppConfig":
        return cls(
            project=ProjectConfig(**data["project"]),
            runtime=RuntimeConfig(**data["runtime"]),
            game=GameConfig(players=tuple(data["game"]["players"]), **_without(data["game"], "players")),
            prototype=PrototypeConfig(**data["prototype"]),
            search=SearchConfig(**data["search"]),
            training=TrainingConfig(**data["training"]),
            model=ModelConfig(**data["model"]),
            scoring=ScoringConfig(**data["scoring"]),
            heuristic=HeuristicConfig(
                alignment_weights=tuple(data["heuristic"]["alignment_weights"]),
                enemy_alignment_weights=tuple(data["heuristic"]["enemy_alignment_weights"]),
                live_cell_weight=data["heuristic"]["live_cell_weight"],
                candidate_score_weight=data["heuristic"]["candidate_score_weight"],
                terminal_score=data["heuristic"]["terminal_score"],
                include_candidate_edge=data["heuristic"]["include_candidate_edge"],
            ),
            integration=IntegrationConfig(**data["integration"]),
            evaluation=EvaluationConfig(**data["evaluation"]),
        )


def _without(mapping: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: value for key, value in mapping.items() if key not in keys}


def load_config(path: str | Path = "configs/default.toml") -> AppConfig:
    config_path = Path(path)
    with config_path.open("rb") as handle:
        data = tomllib.load(handle)
    return AppConfig.from_mapping(data)
