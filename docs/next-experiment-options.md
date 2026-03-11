# Next Experiment Options

- Generated (UTC): 2026-03-09
- Baseline lane: `configs/fast.toml`
- Current champion: `artifacts/alphazero_cycle_20_fast/cycle_020/bootstrap_model.pt`

## What The 20-Cycle Run Actually Shows

Running the `15 x 15` lane longer did help, but not in a simple "more cycles = more wins every time" way.

What improved:
- policy loss dropped from `4.9326` to `3.3237`
- value loss dropped from `0.00500` to `0.00322`
- every cycle produced a new promoted champion

What plateaued:
- the post-train gate mostly stayed in a narrow band: `8.5` or `9.0` points
- checkpoint gate win rate stayed between `0.708` and `0.75`
- every promotion match from cycle `002` onward finished at the same `4.5 - 1.5`

Practical read:
- yes, longer training is still creating stronger checkpoints under the current gate
- no, the win rate is not climbing cleanly cycle after cycle
- the current lane is improving, but the evaluation is starting to saturate

## Main Ways To Change The System

### 1. More Search Per Move

Change:
- raise `search.root_simulations`

Effect:
- stronger play at fixed model size
- slower self-play and slower evaluation

Why it matters:
- if the current bottleneck is weak conversion search, better MCTS may help more than more training epochs

Low-risk version:
- `24 -> 48`

### 2. Stronger Model

Change:
- increase `model.channels`
- increase `model.blocks`

Effect:
- more capacity to learn patterns the current tiny network may be compressing away
- slower training and inference

Why it matters:
- current model is still very small: `channels = 16`, `blocks = 2`

Low-risk version:
- `channels 16 -> 24`
- `blocks 2 -> 3`

### 3. Less Opening Dependence Over Time

Change:
- reduce `training.bootstrap_seeded_start_fraction`

Effect:
- forces more true-from-root play
- risks returning to low-signal draw-heavy self-play too quickly

Why it matters:
- current training is `75%` seeded starts, which is good for bootstrapping but can limit generalization if left too high forever

Low-risk version:
- start at `0.75`
- step down to `0.50`
- later test `0.25`

### 4. Better Conversion Curriculum

Change:
- expand the opening suite with more defend-then-convert positions

Effect:
- directly targets the current weakness
- does not require more board size or much more compute

Why it matters:
- the current draw cluster is in defend-first openings, not immediate-finish openings

This is the highest-signal change for reducing draws.

### 5. Lower Self-Play Temperature Later In Training

Change:
- reduce `training.self_play_temperature`

Effect:
- less noisy late-cycle self-play
- risks premature collapse if lowered too early

Why it matters:
- once the policy is strong enough, fully hot self-play can keep wasting games on avoidable drift

Low-risk version:
- keep `1.0` early
- test `0.7` in later cycles

### 6. Stronger Evaluation, Not Just Stronger Training

Change:
- expand the promotion suite
- raise `evaluation.promotion_games_per_match`

Effect:
- better measurement
- more expensive cycle gating

Why it matters:
- the current promotion match is probably too weak to separate late checkpoints

This helps us trust improvement. It does not itself make the bot stronger.

## Recommended Next Runs

If the goal is fewer draws:

1. Add more defend-then-convert openings.
2. Raise `root_simulations` from `24` to `48`.
3. Keep board size at `15 x 15`.

If the goal is stronger general play:

1. Keep `15 x 15`.
2. Lower seeded-start fraction gradually: `0.75 -> 0.50`.
3. Raise model size one small step.

If the goal is better confidence in progress:

1. Keep training unchanged.
2. Strengthen the promotion suite and match length.

## Recommendation

Do not change board size for the next run.

Best next experiment:
- keep `15 x 15`
- raise `search.root_simulations` from `24` to `48`
- keep the same network for now
- add more defend-then-convert openings
- keep seeded starts at `0.75` for one more run

That is the cleanest test of whether the current bottleneck is search/conversion rather than board geometry.
