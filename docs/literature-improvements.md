# Literature-Backed Improvements

For the broader cross-paradigm recommendation, see `docs/literature-roadmap.md`.

This repo now incorporates a few changes that line up more closely with the AlphaZero-family literature, while staying within the current factorized-turn Hex6 architecture.

## Papers Reviewed

- AlphaZero: `Mastering Chess and Shogi by Self-Play with a General Reinforcement Learning Algorithm`
  - https://arxiv.org/abs/1712.01815
- MuZero: `Mastering Atari, Go, Chess and Shogi by Planning with a Learned Model`
  - https://arxiv.org/abs/1911.08265
- KataGo: `Accelerating Self-Play Learning in Go`
  - https://arxiv.org/abs/1902.10565
- Go-Exploit: `Targeted Search Control in AlphaZero for Effective Policy Improvement`
  - https://arxiv.org/abs/2302.12359
- Sampled MuZero: `Learning and Planning in Complex Action Spaces`
  - https://arxiv.org/abs/2104.06303

## What We Implemented

### 1. AlphaZero-style self-play temperature schedule

Why:
- AlphaZero does not keep a high exploration temperature for the entire game.
- Go-Exploit also argues that when trajectories begin from more varied start states, less exploratory action selection is needed later in play.

What changed:
- Added `training.self_play_temperature_drop_ply`
- Added `training.self_play_temperature_after_drop`
- Current defaults in the main profiles:
  - early self-play temperature: `1.0`
  - after `24` placement plies: `0.2`

Where:
- `src/hex6/config/schema.py`
- `src/hex6/train/bootstrap.py`
- `configs/default.toml`
- `configs/fast.toml`
- `configs/colab.toml`
- `configs/colab_hour.toml`

Notes:
- In this repo, `ply_count` is per placement, not per full two-stone turn.
- So the cutoff is specified in placement plies, not turns.

### 2. Rolling replay buffer across cycles

Why:
- AlphaZero-family systems train on a window of recent self-play rather than only the newest batch.
- MuZero and later variants also rely heavily on replay-buffered training data.
- The repo already had `training.replay_buffer_size`, but the training loop was not using it.

What changed:
- `run_cycle` now maintains a persistent replay buffer file at the cycle root.
- `train_bootstrap` merges newly generated self-play with the recent buffer window before training.
- Metrics now report both:
  - `examples`: newly generated examples from this run
  - `replay_buffer_examples`: total examples used for training after replay merge

Where:
- `src/hex6/train/bootstrap.py`
- `src/hex6/train/run_cycle.py`

### 3. Recent-replay policy reanalyse

Why:
- Reanalyse is one of the cleanest ways to get stronger targets out of already-paid-for self-play.
- In this repo, the biggest practical win is refreshing stale replay-buffer policy targets with a stronger current MCTS policy.

What changed:
- Added `training.reanalyse_fraction`
- Added `training.reanalyse_max_examples`
- Recent carry-over replay examples can now have their policy target recomputed before training.
- Value targets still stay grounded in the actual game outcome; only the policy target is refreshed.

Where:
- `src/hex6/train/bootstrap.py`
- `configs/local_4h_strongest_v2.toml`

Practical note:
- The first smoke at `256` reanalysed examples was too expensive.
- The tuned lane now uses a smaller cap so reanalyse remains a helpful bias, not the dominant runtime cost.

## What We Already Had That Matches The Literature

### Seeded start states / search control

Why it stays:
- Go-Exploit shows that starting trajectories from varied states can improve value learning and sample efficiency.
- This repo already uses seeded openings mixed with empty-board starts as a practical answer to draw-heavy empty-board self-play.

Where:
- `training.bootstrap_opening_suite`
- `training.bootstrap_seeded_start_fraction`

### Sampled action subsets

Why it stays:
- Sampled MuZero addresses large or complex action spaces by planning over sampled action subsets rather than exhaustive enumeration.
- Hex6 has a large factored two-placement action space, so this repo's candidate-generation + sampled-turn search structure is aligned with that constraint.

Where:
- `src/hex6/prototype/candidate_explorer.py`
- `src/hex6/search/baseline.py`
- `src/hex6/search/guided_mcts.py`

## High-Value Next Literature Ideas

Not yet implemented:

- More efficient search control / archive sampling
  - most relevant source: Go-Exploit
  - https://arxiv.org/abs/2302.12359

- KataGo-style auxiliary targets
  - most relevant source: KataGo
  - https://arxiv.org/abs/1902.10565

- Better root action selection under limited simulations
  - likely next family: Gumbel / sequential-halving style root control
  - not yet integrated into this repo

## Practical Read

The most immediate gains for this repo were not exotic:

- batch self-play to feed the GPU better
- stop exploring at the same temperature forever
- actually use a replay buffer across cycles

Those three changes are a much better fit for the current 15x15 bounded Hex6 lane than jumping directly to a full MuZero-style latent dynamics rewrite.
