param(
    [string]$RepoPath = "C:\Hexagonal tic tac toe",
    [string]$CycleSummaryPath = "artifacts\alphazero_cycle_16h_best\cycle_summary.json",
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"

$repoResolved = (Resolve-Path $RepoPath).Path
$cycleSummaryResolved = (Resolve-Path (Join-Path $repoResolved $CycleSummaryPath)).Path
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $repoResolved "docs\alphazero-cycle-story.md"
}

$venvPython = Join-Path $repoResolved ".venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }

@'
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="ascii"))


def fmt_num(value, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.{digits}f}"


def pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    return f"{100.0 * float(value):.{digits}f}%"


def _svg_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def write_line_chart(path: Path, title: str, labels: list[str], values: list[float], y_label: str, color: str = "#1b5c75") -> None:
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
        y = top + chart_height - ((value / max_value) * chart_height if max_value > 0 else 0.0)
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
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="3" points="{point_string}"/>')
        for (x, y), value, label in zip(points, values, labels):
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}"/>')
            parts.append(f'<text x="{x:.1f}" y="{y - 10:.1f}" text-anchor="middle" font-family="Georgia, serif" font-size="12" fill="#171717">{value:.2f}</text>')
            parts.append(f'<text x="{x:.1f}" y="{top + chart_height + 24}" text-anchor="middle" font-family="Georgia, serif" font-size="12" fill="#5f5a55">{_svg_escape(label)}</text>')

    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="ascii")


def write_bar_chart(path: Path, title: str, labels: list[str], values: list[float], y_label: str, color: str = "#1b5c75") -> None:
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
        parts.append(f'<text x="{left - 10}" y="{y + 5:.1f}" text-anchor="end" font-family="Georgia, serif" font-size="12" fill="#5f5a55">{value:.1f}</text>')

    for index, (label, value) in enumerate(zip(labels, values)):
        x = left + gap * index + (gap - bar_width) / 2
        bar_height = 0 if max_value <= 0 else (value / max_value) * chart_height
        y = top + chart_height - bar_height
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" rx="8" fill="{color}"/>')
        parts.append(f'<text x="{x + bar_width / 2:.1f}" y="{y - 8:.1f}" text-anchor="middle" font-family="Georgia, serif" font-size="12" fill="#171717">{value:.1f}</text>')
        parts.append(f'<text x="{x + bar_width / 2:.1f}" y="{top + chart_height + 24}" text-anchor="middle" font-family="Georgia, serif" font-size="12" fill="#5f5a55">{_svg_escape(label)}</text>')

    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="ascii")


repo = Path(sys.argv[1]).resolve()
cycle_summary_path = Path(sys.argv[2]).resolve()
output_path = Path(sys.argv[3]).resolve()
summary = load_json(cycle_summary_path)

assets_dir = output_path.parent / "cycle-story-assets"
assets_dir.mkdir(parents=True, exist_ok=True)

cycles = summary.get("cycles", [])
labels = [f"{int(cycle['cycle_index']):02d}" for cycle in cycles]

policy_loss = [float((cycle.get("metrics") or {}).get("final_policy_loss", 0.0)) for cycle in cycles]
value_loss = [float((cycle.get("metrics") or {}).get("final_value_loss", 0.0)) for cycle in cycles]
draw_rate = [100.0 * float((cycle.get("post_train_evaluation") or {}).get("draw_rate", 0.0)) for cycle in cycles]
runtime = [float((cycle.get("metrics") or {}).get("total_seconds", 0.0)) for cycle in cycles]
throughput = [float((cycle.get("metrics") or {}).get("self_play_examples_per_second", 0.0)) for cycle in cycles]
replay_size = [float((cycle.get("metrics") or {}).get("replay_buffer_examples", 0.0)) for cycle in cycles]
promotion_delta = [float((cycle.get("promotion") or {}).get("score_delta", 0.0)) for cycle in cycles]
gate_points = [float((cycle.get("post_train_evaluation") or {}).get("checkpoint_points", 0.0)) for cycle in cycles]

write_line_chart(assets_dir / "policy-loss.svg", "Policy Loss By Cycle", labels, policy_loss, "Loss")
write_line_chart(assets_dir / "value-loss.svg", "Value Loss By Cycle", labels, value_loss, "Loss", color="#7a6651")
write_line_chart(assets_dir / "draw-rate.svg", "Post-Train Draw Rate", labels, draw_rate, "Draw rate (%)", color="#8e6c8a")
write_line_chart(assets_dir / "runtime.svg", "Cycle Runtime", labels, runtime, "Seconds", color="#486b2e")
write_line_chart(assets_dir / "throughput.svg", "Self-Play Throughput", labels, throughput, "Examples / second", color="#c26d2d")
write_line_chart(assets_dir / "replay-buffer.svg", "Replay Buffer Growth", labels, replay_size, "Examples", color="#345995")
write_bar_chart(assets_dir / "promotion-delta.svg", "Promotion Margin", labels, promotion_delta, "Score delta", color="#1b5c75")
write_bar_chart(assets_dir / "gate-points.svg", "Post-Train Gate Points", labels, gate_points, "Points", color="#5b8c5a")

first_cycle = cycles[0] if cycles else {}
latest_cycle = cycles[-1] if cycles else {}
first_metrics = first_cycle.get("metrics") or {}
latest_metrics = latest_cycle.get("metrics") or {}
first_post = first_cycle.get("post_train_evaluation") or {}
latest_post = latest_cycle.get("post_train_evaluation") or {}
latest_promo = latest_cycle.get("promotion") or {}

completed = int(summary.get("cycles_completed", 0))
avg_runtime = sum(runtime) / max(len(runtime), 1)
run_started = cycles[0].get("started_at") if cycles else None
generated_at = summary.get("generated_at")

story_lines: list[str] = []
if cycles:
    start_loss = float(first_metrics.get("final_policy_loss", 0.0))
    end_loss = float(latest_metrics.get("final_policy_loss", 0.0))
    if end_loss < start_loss:
        story_lines.append(
            f"The run is learning in the expected direction: policy loss moved from `{start_loss:.4f}` to `{end_loss:.4f}` over the completed cycles."
        )
    if float(latest_metrics.get("replay_buffer_examples", 0.0)) > float(first_metrics.get("replay_buffer_examples", 0.0)):
        story_lines.append(
            f"The replay buffer is doing real work now, growing from `{int(first_metrics.get('replay_buffer_examples', 0))}` to `{int(latest_metrics.get('replay_buffer_examples', 0))}` examples."
        )
    if latest_promo.get("evaluated"):
        story_lines.append(
            f"The latest challenger still promoted cleanly, beating the incumbent by `{fmt_num(latest_promo.get('candidate_points'), 1)} - {fmt_num(latest_promo.get('incumbent_points'), 1)}`."
        )
    if latest_post:
        story_lines.append(
            f"The short gate is still draw-heavy at `{pct(float(latest_post.get('draw_rate', 0.0)), 1)}`, so the promotion lane remains the more informative strength test."
        )

lines: list[str] = []
lines.append("# AlphaZero Cycle Story")
lines.append("")
lines.append(f"- Generated (UTC): {datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')}")
lines.append(f"- Source artifact: `{cycle_summary_path.relative_to(repo)}`")
lines.append(f"- Run started: `{run_started}`" if run_started else "- Run started: `n/a`")
lines.append(f"- Summary generated_at: `{generated_at}`" if generated_at else "- Summary generated_at: `n/a`")
lines.append(f"- Cycles completed so far: `{completed}`")
lines.append(f"- Current best checkpoint: `{summary.get('best_checkpoint')}`")
lines.append("")
lines.append("## The Story So Far")
lines.append("")
for line in story_lines:
    lines.append(f"- {line}")
lines.append("")
lines.append("## Headline Metrics")
lines.append("")
lines.append("| Metric | Value |")
lines.append("|---|---:|")
lines.append(f"| Cycles completed | {completed} |")
lines.append(f"| Average cycle runtime | {fmt_num(avg_runtime)} s |")
lines.append(f"| First policy loss | {fmt_num(first_metrics.get('final_policy_loss'), 4)} |")
lines.append(f"| Latest policy loss | {fmt_num(latest_metrics.get('final_policy_loss'), 4)} |")
lines.append(f"| First replay buffer | {int(first_metrics.get('replay_buffer_examples', 0)) if first_metrics else 0} |")
lines.append(f"| Latest replay buffer | {int(latest_metrics.get('replay_buffer_examples', 0)) if latest_metrics else 0} |")
lines.append(f"| Latest self-play throughput | {fmt_num(latest_metrics.get('self_play_examples_per_second'), 3)} |")
lines.append(f"| Latest gate win rate | {fmt_num(latest_post.get('checkpoint_win_rate'), 3)} |")
lines.append(f"| Latest gate draw rate | {fmt_num(latest_post.get('draw_rate'), 3)} |")
lines.append(f"| Latest promotion margin | {fmt_num(latest_promo.get('score_delta'), 1)} |")
lines.append("")
lines.append("## Milestones")
lines.append("")
lines.append("| Cycle | Policy Loss | Value Loss | Replay Buffer | Gate Points | Promotion Delta |")
lines.append("|---|---:|---:|---:|---:|---:|")
for cycle in cycles:
    metrics = cycle.get("metrics") or {}
    post = cycle.get("post_train_evaluation") or {}
    promo = cycle.get("promotion") or {}
    lines.append(
        f"| `{int(cycle.get('cycle_index', 0)):03d}` | "
        f"{fmt_num(metrics.get('final_policy_loss'), 4)} | "
        f"{fmt_num(metrics.get('final_value_loss'), 6)} | "
        f"{int(metrics.get('replay_buffer_examples', 0))} | "
        f"{fmt_num(post.get('checkpoint_points'), 1)} | "
        f"{fmt_num(promo.get('score_delta'), 1)} |"
    )
lines.append("")
lines.append("## Graphs")
lines.append("")
lines.append("![Policy Loss](cycle-story-assets/policy-loss.svg)")
lines.append("")
lines.append("![Value Loss](cycle-story-assets/value-loss.svg)")
lines.append("")
lines.append("![Replay Buffer](cycle-story-assets/replay-buffer.svg)")
lines.append("")
lines.append("![Self-Play Throughput](cycle-story-assets/throughput.svg)")
lines.append("")
lines.append("![Cycle Runtime](cycle-story-assets/runtime.svg)")
lines.append("")
lines.append("![Post-Train Draw Rate](cycle-story-assets/draw-rate.svg)")
lines.append("")
lines.append("![Promotion Margin](cycle-story-assets/promotion-delta.svg)")
lines.append("")
lines.append("![Post-Train Gate Points](cycle-story-assets/gate-points.svg)")
lines.append("")
lines.append("## How To Read This")
lines.append("")
lines.append("- `policy loss` tells us whether the network is fitting the MCTS visit targets better over time.")
lines.append("- `replay buffer` shows whether later cycles are training on a broader recent history rather than just the latest self-play batch.")
lines.append("- `promotion margin` is the strongest headline signal, because the short gate can saturate while challenger-vs-incumbent still separates checkpoints.")
lines.append("- `draw rate` staying high means the engine is still better at avoiding losses than forcing wins in the defend-first openings.")
lines.append("")
lines.append("## Regenerate")
lines.append("")
lines.append("```powershell")
lines.append(f"powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_cycle_story.ps1 -RepoPath \"{repo}\" -CycleSummaryPath \"{cycle_summary_path.relative_to(repo)}\" -OutputPath \"{output_path}\"")
lines.append("```")

output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text("\n".join(lines) + "\n", encoding="ascii")
print(f"Wrote cycle story: {output_path}")
'@ | & $python - $repoResolved $cycleSummaryResolved $OutputPath
