# AlphaZero 20-Cycle Report

- Generated (UTC): 2026-03-09
- Source artifact: `artifacts/alphazero_cycle_20_fast/cycle_summary.json`
- Engine lane: bounded `15 x 15`, `guided_mcts`, AlphaZero-style self-play, promotion-gated cycles

## Final Outcome

- The run completed all `20` planned cycles.
- Final champion: `artifacts/alphazero_cycle_20_fast/cycle_020/bootstrap_model.pt`
- Every cycle was promoted. `promoted_cycles = [1..20]`.
- There are no live `hex6` Python processes left from the run.

## Headline Metrics

| Metric | Value |
|---|---:|
| Cycles completed | 20 |
| Total runtime | 7534.52 s |
| Total runtime | 125.58 min |
| Average cycle runtime | 376.73 s |
| Fastest cycle | 336.24 s (`cycle_016`) |
| Slowest cycle | 419.59 s (`cycle_008`) |
| Average examples per cycle | 325.6 |
| Example range | 242 to 330 |
| Policy loss | 4.9326 -> 3.3237 |
| Value loss | 0.00500 -> 0.00322 |
| Average post-train win rate | 0.7395 |
| Average post-train draw rate | 0.4749 |
| Best observed draw rate | 0.389 |

## Final Cycle

Cycle `020` finished with:

- `330` examples
- `306` encoded examples
- `396.13 s` self-play time
- `397.60 s` total time
- post-train tournament: `6 wins, 1 loss, 5 draws`
- post-train checkpoint win rate: `0.708`
- post-train draw rate: `0.389`
- promotion match vs incumbent: `4.5 - 1.5`

## What We Learned

1. The AlphaZero-style loop is working.
The strongest clean signal is not the raw loss curve. It is the promotion lane. Every evaluated challenger beat the incumbent strongly enough to promote, and the best checkpoint advanced all the way through cycle `020`.

2. Improvement is real, but the gate is probably saturating.
From cycle `002` onward, every promotion match landed at the same `4.5 - 1.5` score delta. That is good because it means no regression slipped through. It is also a warning that the current promotion match may be too small or too easy to separate later checkpoints.

3. Training got cheaper than expected.
The original rough estimate for `20` cycles was much higher. The actual completed run took about `2.1` hours. That means this lane is cheap enough to iterate on locally without consuming the full 8-hour budget.

4. The model improved while data volume stayed almost flat.
Most cycles produced about `330` examples. So the gain did not come from simply feeding much larger datasets each round. It came from better self-play targets as the champion improved.

5. Draws are still a major part of the game.
The average post-train draw rate stayed at about `47.5%`. Even the best observed draw rate was `38.9%`, not close to zero. So the engine is improving, but it is not yet converting enough games into decisive wins.

6. Losses are rarer than wins, but not eliminated.
The final cycle still lost `1` game in the post-train tournament. Later cycles are strong, but they are not dominating the gate cleanly enough to call the game "solved" for this lane.

7. Policy loss trended down meaningfully.
Dropping from `4.93` to `3.32` across the run is a useful health signal. The network is fitting the visit-distribution targets better over time. Value loss improved too, but more modestly.

## Loss Curves

- Policy loss improved from `4.9326` at cycle `001` to `3.3237` at cycle `020`.
- Value loss improved from `0.00500` to `0.00322`.
- The best observed post-train draw rate improved to `0.389`, but the run-average draw rate was still `0.4749`.
- The graphs are in `docs/executive-review-assets/`:
  - `policy-loss-by-cycle.svg`
  - `value-loss-by-cycle.svg`
  - `draw-rate-by-cycle.svg`

These are per-cycle endpoint curves, not dense within-cycle training traces, because the fast lane trains with `epochs = 1`.

## Why Training Starts From Various Positions

The current self-play lane is not pure from-the-root AlphaZero. It uses a mixed curriculum:

- `75%` seeded opening-suite starts
- `25%` empty-board starts

That is deliberate. The game is draw-heavy and empty-board self-play tends to diffuse. Seeded openings force the model to see tactical positions often enough to learn immediate wins, must-block turns, and short conversion sequences.

This is a practical compromise:

- It is normal for pure AlphaZero to start only from the true initial position.
- It is also normal in harder training settings to use a curriculum or seeded starts if the raw game is too sparse or too draw-saturated.

So the right framing is: this repo is using openings as training scaffolding, not as the final objective.

## Should We Optimize For The Opening

Not by itself.

Openings are useful for:
- bootstrapping tactical competence
- making short-loop evaluation repeatable
- preventing empty-board training from collapsing into low-information draws

Openings are not enough for:
- proving general play strength
- proving defend-then-convert skill
- proving that empty-board convergence has been solved

The practical rule is:
- optimize enough for the opening suite to keep the model tactically sharp
- keep separate evaluation pressure on more defensive and shifted positions so the engine cannot just overfit the easiest starts

## Board Size Check

The board-size ablation is documented separately in `docs/board-size-ablation.md`.

The main conclusion is simple:

- `15 x 15` is not obviously too small
- moving to `19 x 19` did not reduce draw counts on the completed promotion lane
- moving to `25 x 25` on the standard lane did not improve score over `15 x 15`
- larger boards mostly made stalled games take much longer

The strongest warning sign is compute:

- the full `25 x 25` promotion suite did not finish within a `90` minute wall-clock budget

So the current evidence says the main problem is still conversion quality, not board size.

## Practical Conclusions

- Keep the promotion-gated cycle loop. It is doing its job.
- Strengthen the evaluation lane before trusting more tiny improvements. The current promotion result looks too repetitive.
- If the goal is fewer draws, the next work should target conversion pressure, not just longer training.
- The active lane is good enough to keep as the repo default.

## Cleanup Status

- Old stale website processes were stopped.
- The completed 20-cycle training process has already exited.
- Old wrapper automation scripts were removed from `scripts/`.
- The repo now centers on the active AlphaZero lane plus the report generator.

## Key Files

- `artifacts/alphazero_cycle_20_fast/cycle_summary.json`
- `artifacts/alphazero_cycle_20_fast/cycle_020/promotion_match/summary.json`
- `docs/executive-review.md`
