# Board Size Ablation

- Generated (UTC): 2026-03-09
- Champion checkpoint: `artifacts/alphazero_cycle_20_fast/cycle_020/bootstrap_model.pt`
- Opponent: heuristic baseline
- Search lane: `guided_mcts`
- Goal: determine whether `15 x 15` is too small and whether larger boards reduce draw saturation

## Method

- Kept the trained checkpoint fixed.
- Compared the same champion against baseline on multiple board sizes.
- Used two evaluation suites:
  - `standard`: `configs/experiments/opening_suite.toml`
  - `promotion`: `configs/experiments/promotion_opening_suite.toml`
- Used bounded boards with no artificial ply cap. Games ended only on `win` or `board_exhausted`.

## Results

### Standard Suite

| Board | Games | Checkpoint Score | Checkpoint Win Rate | Draw Rate | Board-Exhausted Draws | Avg Plies |
|---|---:|---:|---:|---:|---:|---:|
| `15 x 15` | 6 | 4.0 | 0.667 | 0.333 | 2 | 86.5 |
| `19 x 19` | 6 | 4.5 | 0.750 | 0.500 | 3 | 186.5 |
| `25 x 25` | 6 | 4.0 | 0.667 | 0.333 | 2 | 238.5 |

Sources:
- `artifacts/board_size_ablation/15x15_standard.json`
- `artifacts/board_size_ablation/19x19_standard.json`
- `artifacts/board_size_ablation/25x25_standard.json`

### Promotion Suite

| Board | Games | Checkpoint Score | Checkpoint Win Rate | Draw Rate | Board-Exhausted Draws | Avg Plies |
|---|---:|---:|---:|---:|---:|---:|
| `15 x 15` | 12 | 8.5 | 0.708 | 0.417 | 5 | 102.5 |
| `19 x 19` | 12 | 8.5 | 0.708 | 0.417 | 5 | 162.17 |
| `25 x 25` | not completed | not completed | not completed | not completed | not completed | not completed |

Sources:
- `artifacts/board_size_ablation/15x15_promotion.json`
- `artifacts/board_size_ablation/19x19_promotion.json`

## What Changed As The Board Grew

1. Draws did not go away on the completed lanes.
   - `15 x 15` and `19 x 19` promotion runs had exactly the same `8.5 / 12` score and the same `5` board-exhausted draws.
   - `25 x 25` standard returned to the same `4.0 / 6` score as `15 x 15`.

2. The stalled games got much longer.
   - Standard avg plies rose from `86.5` on `15 x 15` to `186.5` on `19 x 19` and `238.5` on `25 x 25`.
   - Promotion avg plies rose from `102.5` on `15 x 15` to `162.17` on `19 x 19`.

3. Wins moved farther from edges, but that did not improve conversion.
   - On `15 x 15`, decisive checkpoint wins often had `winning_line_edge_distance` around `2-4`.
   - On `19 x 19`, decisive checkpoint wins were more often `4-6` cells from the edge.
   - On `25 x 25` standard, decisive checkpoint wins landed at edge distance `8`.
   - This suggests larger boards reduce edge proximity, but not the underlying defend-then-convert weakness.

4. Larger boards are expensive enough to become their own problem.
   - The full `25 x 25` promotion suite did not finish within a `90` minute wall-clock budget.
   - That is a practical warning: bigger boards raise search cost sharply even when they do not clearly improve outcomes.

## Interpretation

`15 x 15` is not obviously the main reason the engine draws.

The stronger evidence points somewhere else:
- immediate-finish openings stay decisive on every board size tested
- defend-first openings still stall into `board_exhausted` draws on both `15 x 15` and `19 x 19`
- making the board larger mostly delays those stalls instead of converting them into wins

So the current bottleneck looks more like engine weakness than board-size failure:
- the bot can finish obvious tactical wins
- the bot still struggles to defend, keep pressure, and create the next forcing sequence

## Practical Conclusion

- Keep `15 x 15` as the default local training lane for now.
- Do not assume that a larger board will fix convergence.
- Treat larger boards as a separate compute-heavy experiment, not the primary solution.
- If the goal is fewer draws, focus next on conversion after defense rather than immediately increasing board size again.
