# Current State

This file is the fastest way to understand the repo *as it exists now*.

## Supported Workflow

- Primary environment: local machine
- Primary training style: AlphaZero-style self-play with `guided_mcts`
- Primary board: bounded `15 x 15`
- Primary evaluation: tournament / promotion suites on the same bounded board

## Supported Profiles

Use these unless you have a specific reason not to:

- `configs/default.toml`: shared default research lane
- `configs/fast.toml`: fastest local bootstrap/smoke lane
- `configs/play.toml`: website / manual play lane
- `configs/local_4h_strongest_v2.toml`: current strongest stable local cycle lane
- `configs/local_4h_strongest_v2_gumbel.toml`: current strongest experimental local lane with Gumbel-style root control

## Historical / Non-Canonical Profiles

These remain for reproducibility and comparison, but they are not the main surface to optimize against:

- `configs/colab.toml`
- `configs/colab_hour.toml`
- `configs/colab_strongest_v2.toml`
- `configs/colab_job_queue.toml`
- `configs/colab_efficiency_queue.toml`
- `configs/fast_19.toml`
- `configs/fast_25.toml`
- `configs/local_16h_best.toml`
- `configs/local_4h_strongest.toml`
- `configs/experiments/fast_compare_prelit.toml`

## Current Technical Priorities

1. Improve search/control quality, especially root action selection and defend-then-convert play.
2. Keep experiments tight and comparable before broadening the search surface.
3. Continue performance work only where it materially improves strength-per-hour.

## Current Known Bottlenecks

- Strength bottleneck:
  - defend-first conversion still draws too often
- Runtime bottleneck:
  - baseline turn enumeration and candidate evaluation still dominate end-to-end time more than SGD

## Current Canonical Docs

Read in this order:

1. `README.md`
2. `AGENTS.md`
3. `docs/index.md`
4. `docs/current-state.md`
5. `docs/architecture.md`
6. `docs/tools.md`

## Historical Materials

Historical run reports, old experiment notes, and optional remote-workflow docs are listed in `docs/archive.md`.
