# Experiment Report

## Current measurement status

The repository now has two useful measurement paths:

- checkpoint vs baseline arena with Elo snapshots,
- search-variant matrix runs from a config file.

## What was run

The search matrix in `configs/experiments/search_matrix.toml` compared six search-side
changes against the current interactive-play baseline:

1. `candidate_edge`
2. `wider_first`
3. `wider_pairs`
4. `reply_depth`
5. `frontier_expand`
6. `island_seeds`

The latest summary was written to `artifacts/search_matrix/summary.json`.

## Result

All six variants drew all four games against the baseline in the current whole-game arena.
That means the current Elo harness is too symmetric and too draw-heavy to separate these
variants reliably.

## What this implies

- There is no evidence yet that a longer training run alone will pay off strongly.
- There is also no evidence yet that the tested search tweaks are materially stronger in the
  current arena.
- The highest-value next measurement improvement is an opening suite or tactical benchmark set
  that breaks symmetry and reduces draw saturation.

## Practical conclusion

For the live website, keep the current interactive config as the default production bot until a
better benchmark distinguishes stronger settings.

For research, prioritize:

1. opening-suite evaluation,
2. sharper tactical benchmarks,
3. stronger candidate-generation logic,
4. only then larger training budgets.
