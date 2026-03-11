# Strongest V2 A/B

_Generated 2026-03-10 UTC_

## What Changed

- stronger bootstrap suite: `configs/experiments/bootstrap_conversion_opening_suite_v2.toml`
- stronger search profile: `root_simulations = 96`, `parallel_expansions_per_root = 6`
- moderate model bump: `blocks = 3`
- recent-replay policy reanalyse: `reanalyse_fraction = 0.125`, `reanalyse_max_examples = 64`
- warm-start now loads compatible tensors so the `3`-block model can inherit the old `2`-block checkpoint

Main files:
- `configs/local_4h_strongest_v2.toml`
- `src/hex6/train/bootstrap.py`
- `src/hex6/search/guided_mcts.py`
- `src/hex6/search/model_guided.py`
- `src/hex6/nn/model.py`

## Data-Informed Decision

I tested the old and new lanes from the same starting checkpoint:

- start checkpoint: `artifacts/alphazero_cycle_4h_strongest/cycle_005/bootstrap_model.pt`
- old smoke: `artifacts/compare_strong_old_smoke/metrics.json`
- new smoke: `artifacts/compare_strong_v2_smoke/metrics.json`
- head-to-head: `artifacts/compare_strong_old_vs_v2/summary.json`

### Old lane

- config: `configs/local_4h_strongest.toml`
- total seconds: `226.237`
- self-play seconds: `205.747`
- reanalysed examples: `0`
- gate result: `3.5 / 6`

### New lane

- config: `configs/local_4h_strongest_v2.toml`
- total seconds: `333.904`
- self-play seconds: `264.969`
- replay reanalyse seconds: `59.605`
- reanalysed examples: `64`
- gate result: `4.5 / 6`

### Head-to-head

- `v2_smoke` beat `old_smoke` `9.0 - 3.0`
- result split: `6 wins, 6 draws, 0 losses`

## Practical Read

- The upgrade is stronger.
- The extra runtime is real but acceptable.
- Reanalyse helped, but only after cutting it down. An earlier `256`-example reanalyse cap was too expensive.

So the chosen amount is:

- keep `reanalyse_fraction = 0.125`
- cap it at `64` examples
- keep the `3`-block model bump
- keep the stronger `96`-simulation search

That is the current best tradeoff between strength and wall-clock cost in this repo.
