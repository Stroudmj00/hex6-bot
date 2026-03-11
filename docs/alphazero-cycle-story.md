# AlphaZero Cycle Story

- Generated (UTC): 2026-03-10T07:06:43Z
- Source artifact: `artifacts\alphazero_cycle_16h_best\cycle_summary.json`
- Run started: `2026-03-10T04:59:59Z`
- Summary generated_at: `2026-03-10T06:55:45Z`
- Cycles completed so far: `2`
- Current best checkpoint: `artifacts\alphazero_cycle_16h_best\cycle_002\bootstrap_model.pt`

## The Story So Far

- The run is learning in the expected direction: policy loss moved from `3.2358` to `3.1118` over the completed cycles.
- The replay buffer is doing real work now, growing from `5244` to `10488` examples.
- The latest challenger still promoted cleanly, beating the incumbent by `18.0 - 12.0`.
- The short gate is still draw-heavy at `50.0%`, so the promotion lane remains the more informative strength test.

## Headline Metrics

| Metric | Value |
|---|---:|
| Cycles completed | 2 |
| Average cycle runtime | 981.24 s |
| First policy loss | 3.2358 |
| Latest policy loss | 3.1118 |
| First replay buffer | 5244 |
| Latest replay buffer | 10488 |
| Latest self-play throughput | 5.552 |
| Latest gate win rate | 0.750 |
| Latest gate draw rate | 0.500 |
| Latest promotion margin | 6.0 |

## Milestones

| Cycle | Policy Loss | Value Loss | Replay Buffer | Gate Points | Promotion Delta |
|---|---:|---:|---:|---:|---:|
| `001` | 3.2358 | 0.000001 | 5244 | 9.0 | 6.5 |
| `002` | 3.1118 | 0.000000 | 10488 | 9.0 | 6.0 |

## Graphs

![Policy Loss](cycle-story-assets/policy-loss.svg)

![Value Loss](cycle-story-assets/value-loss.svg)

![Replay Buffer](cycle-story-assets/replay-buffer.svg)

![Self-Play Throughput](cycle-story-assets/throughput.svg)

![Cycle Runtime](cycle-story-assets/runtime.svg)

![Post-Train Draw Rate](cycle-story-assets/draw-rate.svg)

![Promotion Margin](cycle-story-assets/promotion-delta.svg)

![Post-Train Gate Points](cycle-story-assets/gate-points.svg)

## How To Read This

- `policy loss` tells us whether the network is fitting the MCTS visit targets better over time.
- `replay buffer` shows whether later cycles are training on a broader recent history rather than just the latest self-play batch.
- `promotion margin` is the strongest headline signal, because the short gate can saturate while challenger-vs-incumbent still separates checkpoints.
- `draw rate` staying high means the engine is still better at avoiding losses than forcing wins in the defend-first openings.

## Regenerate

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_cycle_story.ps1 -RepoPath "C:\Hexagonal tic tac toe" -CycleSummaryPath "artifacts\alphazero_cycle_16h_best\cycle_summary.json" -OutputPath "C:\Hexagonal tic tac toe\docs\alphazero-cycle-story.md"
```
