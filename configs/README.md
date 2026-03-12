# Config Matrix

This repo keeps a small set of current profiles and a larger set of historical comparison profiles.

## Current Profiles

- `default.toml`: shared default research lane
- `fast.toml`: fastest local bootstrap / smoke lane
- `play.toml`: local website / interactive play
- `local_4h_strongest_v2.toml`: strongest stable local cycle lane
- `local_4h_strongest_v2_gumbel.toml`: strongest experimental local cycle lane

## Historical Profiles

These are retained for reproducibility and artifact comparison, but they are not the default optimization target:

- `colab.toml`
- `colab_hour.toml`
- `colab_strongest_v2.toml`
- `colab_job_queue.toml`
- `colab_efficiency_queue.toml`
- `fast_19.toml`
- `fast_25.toml`
- `local_16h_best.toml`
- `local_4h_strongest.toml`
- `experiments/fast_compare_prelit.toml`

## Experiment Suites

- `experiments/bootstrap_conversion_opening_suite*.toml`: seeded training starts
- `experiments/conversion_opening_suite.toml`: short post-train gate
- `experiments/promotion_conversion_opening_suite.toml`: promotion lane
- `experiments/search_matrix.toml`: search/eval sweeps
