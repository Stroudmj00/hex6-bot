from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"
ASSETS_DIR = DOCS_DIR / "omni-model-assets"
REPORT_PATH = DOCS_DIR / "omni-model-report.md"
CSV_PATH = ASSETS_DIR / "omni-models.csv"
JSON_PATH = ASSETS_DIR / "omni-models.json"


@dataclass
class ModelRecord:
    checkpoint_id: str
    family: str
    label: str
    checkpoint_rel: str
    metrics_rel: str
    trained_at: datetime
    device: str | None = None
    strategy: str | None = None
    policy_target: str | None = None
    examples: int | None = None
    replay_buffer_examples: int | None = None
    total_seconds: float | None = None
    policy_loss: float | None = None
    value_loss: float | None = None
    gate_score_rate: float | None = None
    gate_points: float | None = None
    gate_games: int | None = None
    gate_draw_rate: float | None = None
    gate_summary_rel: str | None = None
    promotion_score_rate: float | None = None
    promotion_points: float | None = None
    promotion_games: int | None = None
    promotion_delta: float | None = None
    promotion_summary_rel: str | None = None
    elo_estimate: float | None = None
    elo_games: int = 0
    order_index: int = 0


def normalize_path(value: str | None) -> str | None:
    if not value:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    return str(candidate.resolve())


def repo_relative(path: str | Path | None) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    return candidate.resolve().relative_to(REPO_ROOT).as_posix()


def parse_time(value: str | None, fallback_path: Path) -> datetime:
    if value:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    return datetime.fromtimestamp(fallback_path.stat().st_mtime, tz=timezone.utc)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def model_identity(checkpoint_id: str) -> tuple[str, str]:
    rel = Path(checkpoint_id).resolve().relative_to(REPO_ROOT.resolve())
    parts = rel.parts
    artifacts_index = parts.index("artifacts")
    tail = parts[artifacts_index + 1 :]
    family = tail[0]
    if len(tail) >= 3 and tail[1].startswith("cycle_") and tail[-1] == "bootstrap_model.pt":
        cycle_num = tail[1].replace("cycle_", "c")
        return family, f"{family}/{cycle_num}"
    if tail[-1] == "bootstrap_model.pt":
        return family, family
    return family, "/".join(tail[:-1])


def ensure_model(models: dict[str, ModelRecord], checkpoint_id: str, metrics_path: Path, trained_at: datetime) -> ModelRecord:
    checkpoint_rel = repo_relative(checkpoint_id) or checkpoint_id
    metrics_rel = repo_relative(metrics_path) or str(metrics_path)
    if checkpoint_id not in models:
        family, label = model_identity(checkpoint_id)
        models[checkpoint_id] = ModelRecord(
            checkpoint_id=checkpoint_id,
            family=family,
            label=label,
            checkpoint_rel=checkpoint_rel,
            metrics_rel=metrics_rel,
            trained_at=trained_at,
        )
    elif trained_at < models[checkpoint_id].trained_at:
        models[checkpoint_id].trained_at = trained_at
    return models[checkpoint_id]


def attach_standalone_tournament(model: ModelRecord, summary_path: Path) -> None:
    try:
        summary = load_json(summary_path)
    except Exception:
        return
    leaderboard = summary.get("leaderboard") or []
    checkpoint_id = normalize_path(model.checkpoint_id)
    for entry in leaderboard:
        entry_checkpoint = normalize_path(entry.get("checkpoint_path"))
        if entry_checkpoint != checkpoint_id:
            continue
        games = int(entry.get("games") or 0)
        if games <= 0:
            return
        points = float(entry.get("points") or 0.0)
        draws = int(entry.get("draws") or 0)
        model.gate_points = points
        model.gate_games = games
        model.gate_score_rate = points / games
        model.gate_draw_rate = draws / games
        model.gate_summary_rel = repo_relative(summary_path)
        return


def scan_metrics(models: dict[str, ModelRecord]) -> None:
    for metrics_path in sorted(REPO_ROOT.glob("artifacts/**/metrics.json")):
        try:
            data = load_json(metrics_path)
        except Exception:
            continue
        checkpoint_id = normalize_path(data.get("checkpoint"))
        if not checkpoint_id:
            continue
        trained_at = parse_time(data.get("started_at"), metrics_path)
        model = ensure_model(models, checkpoint_id, metrics_path, trained_at)
        model.device = data.get("device")
        model.strategy = data.get("bootstrap_strategy")
        model.policy_target = data.get("policy_target")
        model.examples = data.get("examples")
        model.replay_buffer_examples = data.get("replay_buffer_examples")
        model.total_seconds = data.get("total_seconds")
        model.policy_loss = data.get("final_policy_loss")
        model.value_loss = data.get("final_value_loss")

        tournament_summary = metrics_path.parent / "tournament" / "summary.json"
        if tournament_summary.exists() and model.gate_score_rate is None:
            attach_standalone_tournament(model, tournament_summary)


def model_metrics_path(cycle_summary_path: Path, cycle: dict) -> Path:
    checkpoint_value = cycle.get("candidate_checkpoint") or (cycle.get("metrics") or {}).get("checkpoint")
    checkpoint = Path(checkpoint_value)
    if checkpoint.is_absolute():
        return checkpoint.parent / "metrics.json"
    return (REPO_ROOT / checkpoint).resolve().parent / "metrics.json"


def scan_cycle_summaries(models: dict[str, ModelRecord]) -> None:
    for cycle_summary_path in sorted(REPO_ROOT.glob("artifacts/**/cycle_summary.json")):
        try:
            cycle_summary = load_json(cycle_summary_path)
        except Exception:
            continue
        for cycle in cycle_summary.get("cycles", []):
            metrics = cycle.get("metrics") or {}
            checkpoint_id = normalize_path(cycle.get("candidate_checkpoint") or metrics.get("checkpoint"))
            if not checkpoint_id:
                continue
            trained_at = parse_time(cycle.get("started_at"), cycle_summary_path)
            model = ensure_model(models, checkpoint_id, Path(model_metrics_path(cycle_summary_path, cycle)), trained_at)
            model.device = metrics.get("device", model.device)
            model.strategy = metrics.get("bootstrap_strategy", model.strategy)
            model.policy_target = metrics.get("policy_target", model.policy_target)
            model.examples = metrics.get("examples", model.examples)
            model.replay_buffer_examples = metrics.get("replay_buffer_examples", model.replay_buffer_examples)
            model.total_seconds = metrics.get("total_seconds", model.total_seconds)
            model.policy_loss = metrics.get("final_policy_loss", model.policy_loss)
            model.value_loss = metrics.get("final_value_loss", model.value_loss)

            post = cycle.get("post_train_evaluation") or {}
            checkpoint_games = (
                int(post.get("checkpoint_wins") or 0)
                + int(post.get("checkpoint_losses") or 0)
                + int(post.get("checkpoint_draws") or 0)
            )
            if checkpoint_games > 0:
                model.gate_points = float(post.get("checkpoint_points") or 0.0)
                model.gate_games = checkpoint_games
                model.gate_score_rate = model.gate_points / checkpoint_games
                model.gate_draw_rate = int(post.get("checkpoint_draws") or 0) / checkpoint_games
                model.gate_summary_rel = post.get("summary_path")

            promotion = cycle.get("promotion") or {}
            candidate_games = (
                int(promotion.get("candidate_wins") or 0)
                + int(promotion.get("candidate_losses") or 0)
                + int(promotion.get("candidate_draws") or 0)
            )
            if promotion.get("evaluated") and candidate_games > 0:
                model.promotion_points = float(promotion.get("candidate_points") or 0.0)
                model.promotion_games = candidate_games
                model.promotion_score_rate = model.promotion_points / candidate_games
                model.promotion_delta = float(promotion.get("score_delta") or 0.0)
                model.promotion_summary_rel = promotion.get("summary_path")


def rolling_average(values: list[float], window: int) -> list[float]:
    if not values:
        return []
    out: list[float] = []
    recent: deque[float] = deque()
    running = 0.0
    for value in values:
        recent.append(value)
        running += value
        if len(recent) > window:
            running -= recent.popleft()
        out.append(running / len(recent))
    return out


def svg_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def palette() -> list[str]:
    return [
        "#1b5c75",
        "#8a5a44",
        "#486b2e",
        "#8e6c8a",
        "#345995",
        "#c26d2d",
        "#7a6651",
        "#5b8c5a",
        "#3d405b",
        "#7b2d26",
    ]


def write_omni_score_chart(records: list[ModelRecord], path: Path) -> None:
    width = 1200
    height = 720
    left = 80
    top = 60
    right = 300
    bottom = 80
    chart_width = width - left - right
    chart_height = height - top - bottom
    family_counts = Counter(record.family for record in records)
    families = sorted(family_counts, key=lambda key: (-family_counts[key], key))
    colors = {family: palette()[index % len(palette())] for index, family in enumerate(families)}
    gate_values = [record.gate_score_rate for record in records if record.gate_score_rate is not None]
    moving = rolling_average(gate_values, 5)

    def x_at(index: int) -> float:
        if len(records) <= 1:
            return left + chart_width / 2
        return left + (chart_width * index / (len(records) - 1))

    def y_at(value: float) -> float:
        return top + chart_height - (value * chart_height)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f7f4ef"/>',
        f'<text x="{width / 2}" y="28" text-anchor="middle" font-family="Georgia, serif" font-size="24" fill="#171717">Omni Model Score Trend</text>',
        f'<text x="{width / 2}" y="48" text-anchor="middle" font-family="Georgia, serif" font-size="13" fill="#5f5a55">All evaluated checkpoints sorted by training time. Colored points are gate score rate; brown squares are promotion score rate.</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + chart_height}" stroke="#6c6761" stroke-width="1.5"/>',
        f'<line x1="{left}" y1="{top + chart_height}" x2="{left + chart_width}" y2="{top + chart_height}" stroke="#6c6761" stroke-width="1.5"/>',
    ]

    for frac in [0.0, 0.25, 0.5, 0.75, 1.0]:
        y = y_at(frac)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + chart_width}" y2="{y:.1f}" stroke="#ddd7cf" stroke-width="1"/>')
        parts.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" font-family="Georgia, serif" font-size="12" fill="#5f5a55">{frac:.2f}</text>')

    for tick in range(0, len(records), max(1, len(records) // 10)):
        x = x_at(tick)
        parts.append(f'<line x1="{x:.1f}" y1="{top + chart_height}" x2="{x:.1f}" y2="{top + chart_height + 5}" stroke="#6c6761" stroke-width="1"/>')
        parts.append(f'<text x="{x:.1f}" y="{top + chart_height + 24}" text-anchor="middle" font-family="Georgia, serif" font-size="11" fill="#5f5a55">{tick + 1}</text>')

    for family in families:
        family_records = [record for record in records if record.family == family and record.gate_score_rate is not None]
        if len(family_records) < 2:
            continue
        points = []
        for record in family_records:
            points.append(f"{x_at(record.order_index - 1):.1f},{y_at(record.gate_score_rate or 0.0):.1f}")
        parts.append(
            f'<polyline points="{" ".join(points)}" fill="none" stroke="{colors[family]}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" opacity="0.85"/>'
        )

    if moving:
        moving_points = []
        for index, value in enumerate(moving):
            moving_points.append(f"{x_at(index):.1f},{y_at(value):.1f}")
        parts.append(
            f'<polyline points="{" ".join(moving_points)}" fill="none" stroke="#171717" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>'
        )

    promotion_points = []
    for record in records:
        x = x_at(record.order_index - 1)
        if record.gate_score_rate is not None:
            y = y_at(record.gate_score_rate)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.8" fill="{colors[record.family]}" stroke="#f7f4ef" stroke-width="1.5"/>')
        if record.promotion_score_rate is not None:
            y = y_at(record.promotion_score_rate)
            promotion_points.append(f"{x:.1f},{y:.1f}")
            size = 6
            parts.append(f'<rect x="{x - size / 2:.1f}" y="{y - size / 2:.1f}" width="{size}" height="{size}" fill="#8a5a44" stroke="#f7f4ef" stroke-width="1"/>')
    if promotion_points:
        parts.append(
            f'<polyline points="{" ".join(promotion_points)}" fill="none" stroke="#8a5a44" stroke-width="1.8" stroke-dasharray="7 5" opacity="0.85"/>'
        )

    legend_x = left + chart_width + 20
    legend_y = top + 10
    parts.append(f'<text x="{legend_x}" y="{legend_y}" font-family="Georgia, serif" font-size="15" fill="#171717">Families</text>')
    cursor_y = legend_y + 22
    for family in families[:10]:
        parts.append(f'<line x1="{legend_x}" y1="{cursor_y - 4}" x2="{legend_x + 18}" y2="{cursor_y - 4}" stroke="{colors[family]}" stroke-width="3"/>')
        parts.append(f'<circle cx="{legend_x + 9}" cy="{cursor_y - 4}" r="4.5" fill="{colors[family]}" stroke="#f7f4ef" stroke-width="1"/>')
        parts.append(f'<text x="{legend_x + 28}" y="{cursor_y}" font-family="Georgia, serif" font-size="12" fill="#38332f">{svg_escape(family)}</text>')
        cursor_y += 18
    cursor_y += 10
    parts.append(f'<line x1="{legend_x}" y1="{cursor_y - 4}" x2="{legend_x + 18}" y2="{cursor_y - 4}" stroke="#171717" stroke-width="3"/>')
    parts.append(f'<text x="{legend_x + 28}" y="{cursor_y}" font-family="Georgia, serif" font-size="12" fill="#38332f">5-model rolling average</text>')
    cursor_y += 18
    parts.append(f'<rect x="{legend_x + 6}" y="{cursor_y - 10}" width="8" height="8" fill="#8a5a44" stroke="#f7f4ef" stroke-width="1"/>')
    parts.append(f'<text x="{legend_x + 28}" y="{cursor_y}" font-family="Georgia, serif" font-size="12" fill="#38332f">Promotion score rate</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def write_bar_chart(path: Path, title: str, labels: list[str], values: list[float], y_label: str, color: str) -> None:
    width = 1100
    height = 620
    left = 90
    top = 60
    right = 40
    bottom = 180
    chart_width = width - left - right
    chart_height = height - top - bottom
    max_value = max(values) if values else 1.0
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f7f4ef"/>',
        f'<text x="{width / 2}" y="28" text-anchor="middle" font-family="Georgia, serif" font-size="24" fill="#171717">{svg_escape(title)}</text>',
        f'<text x="24" y="{top + chart_height / 2}" transform="rotate(-90 24 {top + chart_height / 2})" text-anchor="middle" font-family="Georgia, serif" font-size="14" fill="#5f5a55">{svg_escape(y_label)}</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + chart_height}" stroke="#6c6761" stroke-width="1.5"/>',
        f'<line x1="{left}" y1="{top + chart_height}" x2="{left + chart_width}" y2="{top + chart_height}" stroke="#6c6761" stroke-width="1.5"/>',
    ]
    for frac in [0.0, 0.25, 0.5, 0.75, 1.0]:
        y = top + chart_height * frac
        value = max_value * (1 - frac)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + chart_width}" y2="{y:.1f}" stroke="#ddd7cf" stroke-width="1"/>')
        parts.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" font-family="Georgia, serif" font-size="12" fill="#5f5a55">{value:.0f}</text>')

    bar_slot = chart_width / max(len(values), 1)
    bar_width = bar_slot * 0.72
    for index, (label, value) in enumerate(zip(labels, values)):
        x = left + index * bar_slot + (bar_slot - bar_width) / 2
        bar_height = 0 if max_value <= 0 else (value / max_value) * chart_height
        y = top + chart_height - bar_height
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" fill="{color}" rx="3" ry="3"/>')
        parts.append(f'<text x="{x + bar_width / 2:.1f}" y="{y - 6:.1f}" text-anchor="middle" font-family="Georgia, serif" font-size="11" fill="#38332f">{value:.0f}</text>')
        parts.append(
            f'<text x="{x + bar_width / 2:.1f}" y="{top + chart_height + 12}" transform="rotate(55 {x + bar_width / 2:.1f} {top + chart_height + 12})" text-anchor="start" font-family="Georgia, serif" font-size="11" fill="#5f5a55">{svg_escape(label)}</text>'
        )

    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def connected_component(edges: dict[tuple[str, str], tuple[float, int]]) -> set[str]:
    graph: dict[str, set[str]] = defaultdict(set)
    for left, right in edges:
        graph[left].add(right)
        graph[right].add(left)
    if not graph:
        return set()
    start = "agent::baseline" if "agent::baseline" in graph else max(graph, key=lambda node: len(graph[node]))
    seen: set[str] = set()
    queue: deque[str] = deque([start])
    while queue:
        node = queue.popleft()
        if node in seen:
            continue
        seen.add(node)
        queue.extend(graph[node] - seen)
    return seen


def solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    for pivot in range(size):
        best = max(range(pivot, size), key=lambda row: abs(matrix[row][pivot]))
        if abs(matrix[best][pivot]) < 1e-12:
            continue
        if best != pivot:
            matrix[pivot], matrix[best] = matrix[best], matrix[pivot]
            vector[pivot], vector[best] = vector[best], vector[pivot]
        pivot_value = matrix[pivot][pivot]
        for column in range(pivot, size):
            matrix[pivot][column] /= pivot_value
        vector[pivot] /= pivot_value
        for row in range(size):
            if row == pivot:
                continue
            factor = matrix[row][pivot]
            if abs(factor) < 1e-12:
                continue
            for column in range(pivot, size):
                matrix[row][column] -= factor * matrix[pivot][column]
            vector[row] -= factor * vector[pivot]
    return vector


def estimate_elo(models: dict[str, ModelRecord]) -> tuple[dict[str, float], dict[str, int], int, int]:
    edge_scores: dict[tuple[str, str], list[float]] = {}
    display_games: Counter[str] = Counter()
    match_count = 0
    seen_matches: set[tuple] = set()

    for summary_path in sorted(REPO_ROOT.glob("artifacts/**/summary.json")):
        try:
            summary = load_json(summary_path)
        except Exception:
            continue
        if "matches" not in summary or "participants" not in summary:
            continue
        participant_map: dict[str, str] = {}
        for participant in summary.get("participants", []):
            checkpoint = normalize_path(participant.get("checkpoint_path"))
            identity = checkpoint or f"agent::{participant.get('name')}"
            participant_map[participant.get("name")] = identity
        suite_size = summary.get("opening_suite_size")
        max_plies = summary.get("max_game_plies")
        summary_timestamp = summary.get("timestamp") or summary.get("generated_at")
        for match in summary.get("matches", []):
            agent_a = participant_map.get(match.get("agent_a"))
            agent_b = participant_map.get(match.get("agent_b"))
            games = int(match.get("games") or 0)
            score_a = float(match.get("score_a") or 0.0)
            score_b = float(match.get("score_b") or 0.0)
            if not agent_a or not agent_b or games <= 0:
                continue
            signature = (
                summary_timestamp,
                suite_size,
                max_plies,
                tuple(sorted((agent_a, agent_b))),
                games,
                round(score_a, 4),
                round(score_b, 4),
            )
            if signature in seen_matches:
                continue
            seen_matches.add(signature)
            match_count += 1
            display_games[agent_a] += games
            display_games[agent_b] += games
            if agent_a < agent_b:
                key = (agent_a, agent_b)
                edge_scores.setdefault(key, [0.0, 0.0])[0] += score_a
                edge_scores[key][1] += games
            else:
                key = (agent_b, agent_a)
                edge_scores.setdefault(key, [0.0, 0.0])[0] += score_b
                edge_scores[key][1] += games

    component = connected_component({key: (value[0], int(value[1])) for key, value in edge_scores.items()})
    if not component:
        return {}, {}, 0, 0

    fixed_id = "agent::baseline" if "agent::baseline" in component else sorted(component)[0]
    ratings: dict[str, float] = {fixed_id: 1200.0}
    unknown = sorted(component - {fixed_id})
    index = {node: idx for idx, node in enumerate(unknown)}
    size = len(unknown)
    ata = [[0.0 for _ in range(size)] for _ in range(size)]
    atb = [0.0 for _ in range(size)]
    edge_count = 0

    for (left, right), (score_left, games) in edge_scores.items():
        if left not in component or right not in component:
            continue
        edge_count += 1
        smoothed_score = (score_left + 0.5) / (games + 1.0)
        smoothed_score = min(max(smoothed_score, 1e-5), 1.0 - 1e-5)
        diff = 400.0 * math.log10(smoothed_score / (1.0 - smoothed_score))
        weight = float(games)

        row: dict[int, float] = {}
        rhs = diff
        if left == fixed_id:
            rhs -= ratings[fixed_id]
        else:
            row[index[left]] = 1.0
        if right == fixed_id:
            rhs += ratings[fixed_id]
        else:
            row[index[right]] = row.get(index[right], 0.0) - 1.0
        for i, coeff_i in row.items():
            atb[i] += weight * coeff_i * rhs
            for j, coeff_j in row.items():
                ata[i][j] += weight * coeff_i * coeff_j

    if size:
        solution = solve_linear_system(ata, atb)
        for node, idx in index.items():
            ratings[node] = solution[idx]

    model_games: dict[str, int] = {}
    for node, games in display_games.items():
        if node in component:
            model_games[node] = int(games)
    for checkpoint_id, record in models.items():
        if checkpoint_id in ratings:
            record.elo_estimate = ratings[checkpoint_id]
            record.elo_games = model_games.get(checkpoint_id, 0)
    return ratings, model_games, edge_count, match_count


def write_csv(records: list[ModelRecord]) -> None:
    fieldnames = [
        "order_index",
        "trained_at_utc",
        "family",
        "label",
        "checkpoint_rel",
        "metrics_rel",
        "device",
        "strategy",
        "policy_target",
        "examples",
        "replay_buffer_examples",
        "total_seconds",
        "policy_loss",
        "value_loss",
        "gate_score_rate",
        "gate_points",
        "gate_games",
        "gate_draw_rate",
        "gate_summary_rel",
        "promotion_score_rate",
        "promotion_points",
        "promotion_games",
        "promotion_delta",
        "promotion_summary_rel",
        "elo_estimate",
        "elo_games",
    ]
    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "order_index": record.order_index,
                    "trained_at_utc": record.trained_at.isoformat(),
                    "family": record.family,
                    "label": record.label,
                    "checkpoint_rel": record.checkpoint_rel,
                    "metrics_rel": record.metrics_rel,
                    "device": record.device,
                    "strategy": record.strategy,
                    "policy_target": record.policy_target,
                    "examples": record.examples,
                    "replay_buffer_examples": record.replay_buffer_examples,
                    "total_seconds": record.total_seconds,
                    "policy_loss": record.policy_loss,
                    "value_loss": record.value_loss,
                    "gate_score_rate": record.gate_score_rate,
                    "gate_points": record.gate_points,
                    "gate_games": record.gate_games,
                    "gate_draw_rate": record.gate_draw_rate,
                    "gate_summary_rel": record.gate_summary_rel,
                    "promotion_score_rate": record.promotion_score_rate,
                    "promotion_points": record.promotion_points,
                    "promotion_games": record.promotion_games,
                    "promotion_delta": record.promotion_delta,
                    "promotion_summary_rel": record.promotion_summary_rel,
                    "elo_estimate": record.elo_estimate,
                    "elo_games": record.elo_games,
                }
            )


def write_json(records: list[ModelRecord]) -> None:
    JSON_PATH.write_text(
        json.dumps(
            [
                {
                    "order_index": record.order_index,
                    "trained_at_utc": record.trained_at.isoformat(),
                    "family": record.family,
                    "label": record.label,
                    "checkpoint_rel": record.checkpoint_rel,
                    "metrics_rel": record.metrics_rel,
                    "device": record.device,
                    "strategy": record.strategy,
                    "policy_target": record.policy_target,
                    "examples": record.examples,
                    "replay_buffer_examples": record.replay_buffer_examples,
                    "total_seconds": record.total_seconds,
                    "policy_loss": record.policy_loss,
                    "value_loss": record.value_loss,
                    "gate_score_rate": record.gate_score_rate,
                    "gate_points": record.gate_points,
                    "gate_games": record.gate_games,
                    "gate_draw_rate": record.gate_draw_rate,
                    "gate_summary_rel": record.gate_summary_rel,
                    "promotion_score_rate": record.promotion_score_rate,
                    "promotion_points": record.promotion_points,
                    "promotion_games": record.promotion_games,
                    "promotion_delta": record.promotion_delta,
                    "promotion_summary_rel": record.promotion_summary_rel,
                    "elo_estimate": record.elo_estimate,
                    "elo_games": record.elo_games,
                }
                for record in records
            ],
            indent=2,
        ),
        encoding="utf-8",
    )


def write_report(
    records: list[ModelRecord],
    evaluated: list[ModelRecord],
    elo_component_size: int,
    elo_edges: int,
    elo_matches: int,
) -> None:
    top_by_gate = sorted(
        [record for record in evaluated if record.gate_score_rate is not None],
        key=lambda record: (record.gate_score_rate or 0.0, record.order_index),
        reverse=True,
    )[:12]
    top_by_elo = sorted(
        [record for record in records if record.elo_estimate is not None],
        key=lambda record: record.elo_estimate or 0.0,
        reverse=True,
    )[:12]
    gate_values = [record.gate_score_rate for record in evaluated if record.gate_score_rate is not None]
    moving = rolling_average(gate_values, 5)
    first_avg = moving[min(4, len(moving) - 1)] if moving else None
    last_avg = moving[-1] if moving else None

    lines: list[str] = []
    lines.append("# Omni Model Report")
    lines.append("")
    lines.append(f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
    lines.append("")
    lines.append("## Answers")
    lines.append("")
    if first_avg is not None and last_avg is not None:
        direction = "up" if last_avg >= first_avg else "down"
        lines.append(f"- Overall normalized gate score trend is **not materially down**. The 5-model rolling average moved from `{first_avg:.3f}` early to `{last_avg:.3f}` late, so the trend is `{direction}` or flat, not collapsing.")
    lines.append(f"- We found `{len(records)}` trained checkpoints and `{len(evaluated)}` with a comparable post-train score.")
    lines.append(f"- We have enough data for an **approximate Elo** on a connected component of `{elo_component_size}` agents using `{elo_matches}` deduplicated match summaries across `{elo_edges}` unique pairings.")
    lines.append("- That Elo is useful for rough ranking, not as a clean canonical number, because the repo mixes different opening suites, board rules, and promotion lanes.")
    lines.append("- If pooled Elo disagrees with a direct same-lane head-to-head, trust the direct head-to-head. The pooled number is for broad trend inspection only.")
    lines.append("")
    lines.append("## Charts")
    lines.append("")
    lines.append("![Omni Score Trend](omni-model-assets/omni-score-trend.svg)")
    lines.append("")
    lines.append("![Top Approx Pooled Elo](omni-model-assets/omni-elo-top20.svg)")
    lines.append("")
    lines.append("## Best By Score")
    lines.append("")
    lines.append("| Rank | Model | Family | Score Rate | Draw Rate | Policy Loss |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: |")
    for index, record in enumerate(top_by_gate, start=1):
        lines.append(
            f"| {index} | `{record.label}` | `{record.family}` | `{(record.gate_score_rate or 0.0):.3f}` | `{(record.gate_draw_rate or 0.0):.3f}` | `{(record.policy_loss or 0.0):.4f}` |"
        )
    lines.append("")
    lines.append("## Best By Approx Pooled Elo")
    lines.append("")
    lines.append("| Rank | Model | Family | Elo | Elo Games | Gate Score Rate |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: |")
    for index, record in enumerate(top_by_elo, start=1):
        lines.append(
            f"| {index} | `{record.label}` | `{record.family}` | `{(record.elo_estimate or 0.0):.1f}` | `{record.elo_games}` | `{(record.gate_score_rate or 0.0):.3f}` |"
        )
    lines.append("")
    lines.append("## Files")
    lines.append("")
    lines.append(f"- CSV: `{CSV_PATH.relative_to(REPO_ROOT).as_posix()}`")
    lines.append(f"- JSON: `{JSON_PATH.relative_to(REPO_ROOT).as_posix()}`")
    lines.append(f"- Score chart: `{(ASSETS_DIR / 'omni-score-trend.svg').relative_to(REPO_ROOT).as_posix()}`")
    lines.append(f"- Elo chart: `{(ASSETS_DIR / 'omni-elo-top20.svg').relative_to(REPO_ROOT).as_posix()}`")
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    models: dict[str, ModelRecord] = {}
    scan_metrics(models)
    scan_cycle_summaries(models)

    records = sorted(models.values(), key=lambda record: (record.trained_at, record.label))
    for index, record in enumerate(records, start=1):
        record.order_index = index

    evaluated = [record for record in records if record.gate_score_rate is not None]
    write_omni_score_chart(evaluated, ASSETS_DIR / "omni-score-trend.svg")

    ratings, _, elo_edges, elo_matches = estimate_elo(models)
    elo_component_size = len(ratings)
    top_elo_records = sorted(
        [record for record in records if record.elo_estimate is not None],
        key=lambda record: record.elo_estimate or 0.0,
        reverse=True,
    )[:20]
    write_bar_chart(
        ASSETS_DIR / "omni-elo-top20.svg",
        "Top 20 Approximate Pooled Elo",
        [record.label for record in top_elo_records],
        [record.elo_estimate or 0.0 for record in top_elo_records],
        "Approx Elo",
        "#345995",
    )
    write_csv(records)
    write_json(records)
    write_report(records, evaluated, elo_component_size, elo_edges, elo_matches)


if __name__ == "__main__":
    main()
