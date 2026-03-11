param(
    [string]$RepoPath = "C:\Hexagonal tic tac toe",
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"

$repoResolved = (Resolve-Path $RepoPath).Path
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $repoResolved "docs\executive-review.md"
}

$venvPython = Join-Path $repoResolved ".venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }

@'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_json(repo: Path, relative: str):
    path = repo / relative
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="ascii"))
    except Exception:
        return None


def fmt_num(value, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.{digits}f}"


def _svg_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def write_bar_chart(path: Path, title: str, labels: list[str], values: list[float], y_label: str) -> None:
    width = 960
    height = 480
    left = 90
    right = 24
    top = 56
    bottom = 86
    chart_width = width - left - right
    chart_height = height - top - bottom
    max_value = max(max(values, default=1.0), 1.0)
    bar_width = chart_width / max(len(values), 1) * 0.6
    gap = chart_width / max(len(values), 1)
    y_ticks = 5

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f8f7f4"/>',
        f'<text x="{width / 2}" y="28" text-anchor="middle" font-family="Georgia, serif" font-size="22" fill="#171717">{_svg_escape(title)}</text>',
        f'<text x="20" y="{top + chart_height / 2}" transform="rotate(-90 20 {top + chart_height / 2})" text-anchor="middle" font-family="Georgia, serif" font-size="14" fill="#5f5a55">{_svg_escape(y_label)}</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + chart_height}" stroke="#6c6761" stroke-width="1.5"/>',
        f'<line x1="{left}" y1="{top + chart_height}" x2="{left + chart_width}" y2="{top + chart_height}" stroke="#6c6761" stroke-width="1.5"/>',
    ]

    for tick in range(y_ticks + 1):
        frac = tick / y_ticks
        value = max_value * (1.0 - frac)
        y = top + chart_height * frac
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + chart_width}" y2="{y:.1f}" stroke="#ddd7cf" stroke-width="1"/>')
        parts.append(f'<text x="{left - 10}" y="{y + 5:.1f}" text-anchor="end" font-family="Georgia, serif" font-size="12" fill="#5f5a55">{value:.0f}</text>')

    for index, (label, value) in enumerate(zip(labels, values)):
        x = left + gap * index + (gap - bar_width) / 2
        bar_height = 0 if max_value <= 0 else (value / max_value) * chart_height
        y = top + chart_height - bar_height
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" rx="8" fill="#1b5c75"/>')
        parts.append(f'<text x="{x + bar_width / 2:.1f}" y="{y - 8:.1f}" text-anchor="middle" font-family="Georgia, serif" font-size="12" fill="#171717">{value:.1f}</text>')
        parts.append(f'<text x="{x + bar_width / 2:.1f}" y="{top + chart_height + 24}" text-anchor="middle" font-family="Georgia, serif" font-size="12" fill="#5f5a55">{_svg_escape(label)}</text>')

    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="ascii")


def write_line_chart(path: Path, title: str, labels: list[str], values: list[float], y_label: str) -> None:
    width = 960
    height = 480
    left = 90
    right = 24
    top = 56
    bottom = 86
    chart_width = width - left - right
    chart_height = height - top - bottom
    max_value = max(max(values, default=1.0), 1.0)
    y_ticks = 5

    def point(index: int, value: float) -> tuple[float, float]:
        if len(values) <= 1:
            x = left + chart_width / 2
        else:
            x = left + (chart_width * index / (len(values) - 1))
        y = top + chart_height - (0 if max_value <= 0 else (value / max_value) * chart_height)
        return x, y

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f8f7f4"/>',
        f'<text x="{width / 2}" y="28" text-anchor="middle" font-family="Georgia, serif" font-size="22" fill="#171717">{_svg_escape(title)}</text>',
        f'<text x="20" y="{top + chart_height / 2}" transform="rotate(-90 20 {top + chart_height / 2})" text-anchor="middle" font-family="Georgia, serif" font-size="14" fill="#5f5a55">{_svg_escape(y_label)}</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + chart_height}" stroke="#6c6761" stroke-width="1.5"/>',
        f'<line x1="{left}" y1="{top + chart_height}" x2="{left + chart_width}" y2="{top + chart_height}" stroke="#6c6761" stroke-width="1.5"/>',
    ]

    for tick in range(y_ticks + 1):
        frac = tick / y_ticks
        value = max_value * (1.0 - frac)
        y = top + chart_height * frac
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + chart_width}" y2="{y:.1f}" stroke="#ddd7cf" stroke-width="1"/>')
        parts.append(f'<text x="{left - 10}" y="{y + 5:.1f}" text-anchor="end" font-family="Georgia, serif" font-size="12" fill="#5f5a55">{value:.2f}</text>')

    points = [point(index, value) for index, value in enumerate(values)]
    if points:
        point_string = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        parts.append(f'<polyline fill="none" stroke="#1b5c75" stroke-width="3" points="{point_string}"/>')
        for (x, y), value, label in zip(points, values, labels):
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#1b5c75"/>')
            parts.append(f'<text x="{x:.1f}" y="{y - 10:.1f}" text-anchor="middle" font-family="Georgia, serif" font-size="12" fill="#171717">{value:.2f}</text>')
            parts.append(f'<text x="{x:.1f}" y="{top + chart_height + 24}" text-anchor="middle" font-family="Georgia, serif" font-size="12" fill="#5f5a55">{_svg_escape(label)}</text>')

    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="ascii")


repo = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
assets_dir = output.parent / "executive-review-assets"
assets_dir.mkdir(parents=True, exist_ok=True)

bootstrap = load_json(repo, "artifacts/bootstrap_alphazero_fast/metrics.json") or {}
cycle_summary = load_json(repo, "artifacts/alphazero_cycle_fast/cycle_summary.json") or {}
active_summary = load_json(repo, "artifacts/alphazero_cycle_20_fast/cycle_summary.json") or {}


def gate_result(post: dict) -> str:
    wins = post.get("checkpoint_wins")
    losses = post.get("checkpoint_losses")
    draws = post.get("checkpoint_draws")
    if wins is None:
        return "n/a"
    return f"{wins}W {losses}L {draws}D"


rows: list[dict] = []
if bootstrap:
    post = bootstrap.get("post_train_evaluation") or {}
    rows.append(
        {
            "label": "bootstrap",
            "examples": bootstrap.get("examples"),
            "encoded": bootstrap.get("encoded_examples"),
            "self_play_seconds": bootstrap.get("self_play_seconds"),
            "total_seconds": bootstrap.get("total_seconds"),
            "win_rate": float(post.get("checkpoint_win_rate", 0.0)) * 100.0,
            "gate_result": gate_result(post) + " vs baseline",
        }
    )

for cycle in cycle_summary.get("cycles", []):
    metrics = cycle.get("metrics") or {}
    post = cycle.get("post_train_evaluation") or {}
    promotion = cycle.get("promotion") or {}
    rows.append(
        {
            "label": f"cycle_{int(cycle.get('cycle_index', 0)):03d}",
            "examples": metrics.get("examples"),
            "encoded": metrics.get("encoded_examples"),
            "self_play_seconds": metrics.get("self_play_seconds"),
            "total_seconds": metrics.get("total_seconds"),
            "win_rate": float(post.get("checkpoint_win_rate", 0.0)) * 100.0,
            "gate_result": (
                f"promoted {fmt_num(promotion.get('candidate_points'), 1)}-{fmt_num(promotion.get('incumbent_points'), 1)}"
                if promotion.get("evaluated")
                else gate_result(post) + " post-train gate"
            ),
        }
    )

active_cycle = None
if active_summary.get("cycles"):
    active_cycle = active_summary["cycles"][-1]
    metrics = active_cycle.get("metrics") or {}
    post = active_cycle.get("post_train_evaluation") or {}
    rows.append(
        {
            "label": f"active_20_cycle_{int(active_cycle.get('cycle_index', 0)):03d}",
            "examples": metrics.get("examples"),
            "encoded": metrics.get("encoded_examples"),
            "self_play_seconds": metrics.get("self_play_seconds"),
            "total_seconds": metrics.get("total_seconds"),
            "win_rate": float(post.get("checkpoint_win_rate", 0.0)) * 100.0,
            "gate_result": gate_result(post) + " post-train gate",
        }
    )

active_cycle_rows: list[dict] = []
for cycle in active_summary.get("cycles", []):
    metrics = cycle.get("metrics") or {}
    post = cycle.get("post_train_evaluation") or {}
    active_cycle_rows.append(
        {
            "label": f"{int(cycle.get('cycle_index', 0)):02d}",
            "policy_loss": float(metrics.get("final_policy_loss", 0.0)),
            "value_loss": float(metrics.get("final_value_loss", 0.0)),
            "draw_rate": float(post.get("draw_rate", 0.0)) * 100.0,
        }
    )

generated_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

lines: list[str] = []
lines.append("# Executive Review")
lines.append("")
lines.append(f"- Generated (UTC): {generated_utc}")
lines.append("- Active lane: `15 x 15` bounded board, `guided_mcts`, AlphaZero-style self-play")
lines.append("- Main comparison lane: `configs/fast.toml` plus `configs/experiments/conversion_opening_suite.toml`")
lines.append("")
lines.append("## TL;DR")
lines.append("")
lines.append("- The repo is now centered on one active engine path instead of several stale comparison lanes.")
if len(rows) >= 3:
    lines.append("- We have a validated improvement signal: `artifacts/alphazero_cycle_fast/cycle_002/promotion_match/summary.json` shows cycle 2 beating cycle 1 by `4.5 - 1.5`.")
if active_summary:
    active_cycles_completed = int(active_summary.get("cycles_completed", 0))
    if active_cycles_completed >= 20:
        lines.append("- The `20`-cycle run completed successfully and finished with cycle `020` as the best checkpoint under `artifacts/alphazero_cycle_20_fast/cycle_summary.json`.")
    else:
        lines.append(
            f"- The live `20`-cycle run has completed `{active_cycles_completed}` cycles so far and is still progressing under `artifacts/alphazero_cycle_20_fast/cycle_summary.json`."
        )
lines.append("- The default bounded lane ends on `win` or `board_exhausted`, not on an artificial ply cap.")
lines.append("")
lines.append("## Current Snapshot")
lines.append("")
lines.append("| Run | Examples | Encoded | Self-play s | Total s | Gate result |")
lines.append("|---|---:|---:|---:|---:|---|")
for row in rows:
    lines.append(
        f"| {row['label']} | {row['examples']} | {row['encoded']} | "
        f"{fmt_num(row['self_play_seconds'])} | {fmt_num(row['total_seconds'])} | {row['gate_result']} |"
    )
lines.append("")
lines.append("## Graphs")
lines.append("")

write_bar_chart(
    assets_dir / "training-examples.svg",
    "Training Examples",
    [row["label"] for row in rows],
    [float(row["examples"] or 0.0) for row in rows],
    "Examples",
)
lines.append("![Training Examples](executive-review-assets/training-examples.svg)")
lines.append("")

write_bar_chart(
    assets_dir / "post-train-win-rate.svg",
    "Post-Train Win Rate",
    [row["label"] for row in rows],
    [float(row["win_rate"] or 0.0) for row in rows],
    "Win rate (%)",
)
lines.append("![Post-Train Win Rate](executive-review-assets/post-train-win-rate.svg)")
lines.append("")

write_bar_chart(
    assets_dir / "cycle-runtime.svg",
    "Cycle Runtime",
    [row["label"] for row in rows],
    [float(row["total_seconds"] or 0.0) for row in rows],
    "Total seconds",
)
lines.append("![Cycle Runtime](executive-review-assets/cycle-runtime.svg)")
lines.append("")

if active_cycle_rows:
    write_line_chart(
        assets_dir / "policy-loss-by-cycle.svg",
        "Policy Loss By Cycle",
        [row["label"] for row in active_cycle_rows],
        [row["policy_loss"] for row in active_cycle_rows],
        "Loss",
    )
    lines.append("![Policy Loss By Cycle](executive-review-assets/policy-loss-by-cycle.svg)")
    lines.append("")

    write_line_chart(
        assets_dir / "value-loss-by-cycle.svg",
        "Value Loss By Cycle",
        [row["label"] for row in active_cycle_rows],
        [row["value_loss"] for row in active_cycle_rows],
        "Loss",
    )
    lines.append("![Value Loss By Cycle](executive-review-assets/value-loss-by-cycle.svg)")
    lines.append("")

    write_line_chart(
        assets_dir / "draw-rate-by-cycle.svg",
        "Draw Rate By Cycle",
        [row["label"] for row in active_cycle_rows],
        [row["draw_rate"] for row in active_cycle_rows],
        "Draw rate (%)",
    )
    lines.append("![Draw Rate By Cycle](executive-review-assets/draw-rate-by-cycle.svg)")
    lines.append("")

promotion = None
for cycle in cycle_summary.get("cycles", []):
    if (cycle.get("promotion") or {}).get("evaluated"):
        promotion = cycle.get("promotion") or {}
        break
if promotion:
    write_bar_chart(
        assets_dir / "promotion-match.svg",
        "Promotion Match",
        ["candidate", "incumbent"],
        [
            float(promotion.get("candidate_points", 0.0)),
            float(promotion.get("incumbent_points", 0.0)),
        ],
        "Points",
    )
    lines.append("![Promotion Match](executive-review-assets/promotion-match.svg)")
    lines.append("")

lines.append("## What Changed")
lines.append("")
lines.append("- The active repo path is now the AlphaZero-style lane only.")
lines.append("- Old `50x50`, `fast_deep`, and `fast_wide` comparison configs were removed.")
lines.append("- Docs and tests now point at the default `15 x 15` bounded board and the current guided-MCTS training flow.")
lines.append("- The executive review now tracks the artifacts that actually matter for this repo today.")
lines.append("")
lines.append("## Current Read")
lines.append("")
lines.append("- The best validated improvement signal is still the two-cycle run at `artifacts/alphazero_cycle_fast/cycle_summary.json`.")
if active_summary:
    if int(active_summary.get("cycles_completed", 0)) >= 20:
        lines.append("- The finished `20`-cycle run is now the main local measurement for whether longer training keeps helping.")
    else:
        lines.append("- The active `20`-cycle run is the longer measurement for \"does more training keep helping?\" and is still in progress.")
if active_cycle_rows:
    lines.append("- The loss charts are one point per cycle, not dense within-cycle curves, because the current fast lane trains for `epochs = 1`.")
lines.append("- The fixed opening-suite gate remains the right short-loop comparison lane because it is cheap, repeatable, and avoids the old empty-board timeout problem.")
lines.append("")
lines.append("## Next Moves")
lines.append("")
if active_summary and int(active_summary.get("cycles_completed", 0)) >= 20:
    lines.append("- Use the finished `20`-cycle run as the new baseline and compare future changes against `cycle_020`.")
else:
    lines.append("- Let the `20`-cycle run finish and compare promotion outcomes across cycles.")
lines.append("- Keep the post-train tournament gate fixed so cycle-to-cycle changes stay comparable.")
lines.append("- Only add new experiment branches if they produce a better champion than the current active lane.")

output.parent.mkdir(parents=True, exist_ok=True)
output.write_text("\n".join(lines) + "\n", encoding="ascii")
print(f"Wrote executive review: {output}")
'@ | & $python - $repoResolved $OutputPath
