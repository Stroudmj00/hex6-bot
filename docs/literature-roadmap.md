# Literature Roadmap For The Strongest Engine

- Generated: 2026-03-10
- Scope: deterministic two-player zero-sum board-game engines with search
- Repo context: known rules, known simulator, sparse/factorized two-placement action space, bounded training board by config

## Executive Read

The best path for this repo is not a full MuZero rewrite.

For a known deterministic board game, the literature points more strongly toward a KataGo-style AlphaZero engine than toward a learned-dynamics engine:

- stronger search control
- better root policy improvement under limited simulations
- graph/transposition-aware search
- better replay/reanalyze
- better curricula and state sampling
- modest model scaling
- multi-board-size or masked-size training only after the search/training loop is solid

Blunt recommendation:

1. Keep the engine in the AlphaZero family.
2. Push it toward KataGo and Gumbel AlphaZero ideas.
3. Only consider MuZero-style learned dynamics later if the explicit simulator becomes the bottleneck or if we move to a partially observed or unknown-dynamics setting.

## Papers Reviewed

### Core board-game RL

- AlphaZero
  - `Mastering Chess and Shogi by Self-Play with a General Reinforcement Learning Algorithm`
  - https://arxiv.org/abs/1712.01815
- Expert Iteration
  - `Thinking Fast and Slow with Deep Learning and Tree Search`
  - https://arxiv.org/abs/1705.08439
- MuZero
  - `Mastering Atari, Go, Chess and Shogi by Planning with a Learned Model`
  - https://arxiv.org/abs/1911.08265
- Gumbel AlphaZero / Gumbel MuZero
  - `Policy improvement by planning with Gumbel`
  - https://openreview.net/forum?id=bERaNdoegnO

### Efficiency and training-system work

- KataGo
  - `Accelerating Self-Play Learning in Go`
  - https://arxiv.org/abs/1902.10565
- KataGo methods note
  - https://github.com/lightvector/KataGo/blob/master/docs/KataGoMethods.md
- Batch MCTS
  - `Batch Monte Carlo Tree Search`
  - https://arxiv.org/abs/2104.04278
- Monte-Carlo Graph Search
  - `Monte-Carlo Graph Search for AlphaZero`
  - https://arxiv.org/abs/2012.11045
- ReZero
  - `ReZero: Boosting MCTS-based Algorithms by Backward-view and Entire-buffer Reanalyze`
  - https://arxiv.org/abs/2404.16364

### Search-control and action-space work

- Go-Exploit
  - `Targeted Search Control in AlphaZero for Effective Policy Improvement`
  - https://arxiv.org/abs/2302.12359
- Sampled MuZero
  - `Learning and Planning in Complex Action Spaces`
  - https://arxiv.org/abs/2104.06303

### Scaling and board-size work

- AlphaZero on Hex scaling
  - `Scaling Scaling Laws with Board Games`
  - https://arxiv.org/abs/2104.03113
- AlphaZero scaling laws
  - `Scaling Laws for a Multi-Agent Reinforcement Learning Model`
  - https://arxiv.org/abs/2210.00849
- Comparative benchmark
  - `MiniZero: Comparative Analysis of AlphaZero and MuZero on Go, Othello, and Atari Games`
  - https://arxiv.org/abs/2310.11305
- Train small, play large
  - `Train on Small, Play the Large: Scaling Up Board Games with AlphaZero and GNN`
  - https://arxiv.org/abs/2107.08387

## What The Literature Says

### 1. For known board-game rules, AlphaZero-style planning remains the default baseline

AlphaZero shows that a policy-value network plus MCTS can reach top strength from self-play alone on board games. Expert Iteration is even more directly relevant for this repo because it explicitly separates planning from generalization and reports strong Hex results.

Why this matters here:

- our game has known deterministic rules
- we already have a working search engine
- the value of a learned dynamics model is lower than in Atari-like settings

Practical read:

- do not abandon explicit-search AlphaZero-style training
- finish the search/training system before moving to learned dynamics

### 2. MuZero is powerful, but it is not the first-best move here

MuZero is most compelling when the environment dynamics are unknown or when observations are high-dimensional and planning in latent space is worth the extra complexity.

For this repo, those benefits are weaker:

- we already know the transition rules exactly
- the current bottleneck is not the absence of a learned model of the game
- the current bottleneck is search quality, conversion, and wall-clock efficiency

Practical read:

- MuZero is a later option, not the next option
- if we implement it too early, we risk adding model error on top of already-challenging search

### 3. KataGo is the strongest direct inspiration

KataGo reports large efficiency gains over plain AlphaZero and many of its improvements are general rather than Go-specific. The official methods note is even more useful than the original paper because it includes later engineering and training discoveries.

The most relevant KataGo ideas for this repo are:

- graph/transposition-aware search
- better replay and target shaping
- policy surprise weighting / harder-example emphasis
- dynamic root-control choices
- auxiliary targets
- size-flexible training via masking

Practical read:

- the repo should move toward KataGo-style AlphaZero, not generic MuZero

### 4. Gumbel root control matters when simulations are limited

Gumbel AlphaZero argues that plain AlphaZero can fail to improve the policy if not enough root actions are explored, and that Gumbel-based policy improvement helps especially when training with few simulations.

This is highly relevant because our local/consumer-GPU regime is almost always low-to-medium simulation count, not DeepMind-scale 800+ simulation board-game training.

Practical read:

- root action selection is not just an implementation detail
- Gumbel-style root selection is one of the highest-value search upgrades after the current batching work

### 5. Better state sampling beats naive initial-state-only self-play

Go-Exploit shows that starting self-play from an archive of states of interest can improve value learning and sample efficiency. This matches what we already observed locally: empty-board-only self-play drifts and draws too often.

Practical read:

- seeded starts are not a hack; they are supported by the literature
- but the state archive should get smarter than a fixed opening list

### 6. Large or factored action spaces justify sampled candidate sets

Sampled MuZero explicitly addresses complex action spaces where exhaustive enumeration is infeasible. Our two-placement turn structure has exactly that property.

Practical read:

- candidate generation is not a temporary workaround
- it is a principled part of the architecture
- the right question is how to sample and rerank candidates better, not whether sampling itself is illegitimate

### 7. Bigger models help, but only when matched to compute

The scaling papers show that AlphaZero-family strength improves predictably with model size and compute, and that larger models can be more sample-efficient. They also show that game size and compute budget trade off directly.

Practical read:

- a moderate network bump is justified
- a giant network bump before search/system improvements is not
- on Colab GPUs, model size should grow only after the inference pipeline is efficient enough

### 8. Multi-board-size training is viable

KataGo's methods document shows that mixed board sizes can be handled with masking and size-independent heads. `Train on Small, Play the Large` and the Hex scaling paper both support the idea that small-board and large-board training can transfer if the architecture is designed for it.

Practical read:

- training on 15x15 only is not the only viable future
- but the right way to expand is masked mixed-size training, not flipping the whole repo to one larger board overnight

## Recommended Roadmap

## Phase 1: Finish The AlphaZero/KataGo Engine

These are the highest-ROI changes now.

### A. Keep AlphaZero, not MuZero

- keep explicit simulator-based search
- keep visit-distribution policy training
- keep self-play plus promotion matches

### B. Upgrade search quality at the root

- implement Gumbel-style root action selection or sequential-halving-style root improvement
- use it first in low-simulation regimes
- compare against current PUCT on the same promotion suite

Why:

- this is the cleanest literature-backed answer to limited-simulation policy improvement

### C. Upgrade from tree search to graph-aware search

- strengthen the current transposition machinery into a real graph-search style MCTS where appropriate
- share information across transpositions instead of duplicating subtrees
- prioritize this because the game has many transpositions from two-placement turns

Why:

- direct board-game literature support
- likely strength and wall-clock gains together

### D. Replace fixed openings with a state archive

- keep current opening suites
- add an archive of hard states:
  - defend-then-convert states
  - high-draw states
  - surprising-value states
  - states where policy and search disagree sharply
- sample some self-play starts from that archive

Why:

- this is the Go-Exploit direction adapted to this repo

### E. Strengthen replay and reanalyze

- keep rolling replay
- add periodic broader buffer reanalyze instead of only tiny recent reanalyze
- bias reanalysis toward high-surprise or high-draw examples

Why:

- ReZero and related work suggest that better reanalyze scheduling can improve wall-clock efficiency and target quality

### F. Add KataGo-style hard-example weighting

- overweight positions where the search target differs sharply from the network prior
- prioritize states from defend-first conversions and stale replay where policy surprise is high

Why:

- directly targets blind spots instead of spending equal effort on easy positions

## Phase 2: Add Capacity And Better Targets

### A. Moderate network bump

Recommended first bump:

- current strong lane -> `channels +25% to +50%`
- `blocks +1`

Do not jump to a huge net until Colab throughput is measured.

### B. Add auxiliary heads

KataGo-style auxiliary targets are promising, but ours should be game-specific.

Most plausible auxiliary targets for this repo:

- threat-map / forced-response map
- open-window or line-completion density
- win-in-k or danger-in-k classification
- board-control / critical-cell occupancy prediction

Why:

- these heads can teach structure that raw win/loss supervision under-teaches

### C. Progressive simulation schedule

- start early cycles with lower simulation counts
- increase simulations as the model improves

Why:

- MiniZero reports gains from progressive simulation in board games
- this should improve strength per wall-clock hour on Colab

## Phase 3: Expand Board-Size Ambition Carefully

### A. Mixed-size masked training

Recommended order:

1. keep default training on `15x15`
2. add mixed batches with `15x15`, `19x19`, `25x25`
3. keep evaluation lanes explicit per board size

Why:

- this is safer than a hard switch to large-board training
- it is supported by KataGo methods and board-size scaling work

### B. Separate training board from evaluation board

- if larger boards reduce `board_exhausted` draws without exploding runtime, use them first as eval lanes
- only later make them part of mixed-size training

## What Not To Do Next

These are attractive, but the literature says they are lower priority here.

### 1. Full MuZero rewrite

Reason:

- wrong bottleneck for a known deterministic board game

### 2. Pure opening optimization

Reason:

- openings are useful scaffolds, but the main weakness is conversion after defense

### 3. Single giant network jump

Reason:

- bigger nets help only if search and batching are already efficient enough

### 4. Bigger-board-only training flip

Reason:

- board-size scaling literature favors measured compute tradeoffs, not abrupt hard switches

## Recommended Order Of Implementation

If the only question is "what should we build next to maximize strength?", this is the order:

1. Gumbel-style root policy improvement
2. stronger graph/transposition-aware MCTS
3. state-archive self-play starts
4. broader replay reanalyze with surprise weighting
5. progressive simulation schedule
6. moderate network bump
7. auxiliary heads
8. mixed-size masked training

## My Recommendation For This Repo

The best engine to aim for is:

- AlphaZero-family
- KataGo-inspired systems improvements
- Gumbel-style root control
- graph-aware MCTS
- archive-sampled self-play starts
- strong replay reanalyze
- modestly larger network
- eventually mixed-size training

In other words:

build the strongest explicit-search board-game engine first, not the fanciest latent-dynamics engine.
