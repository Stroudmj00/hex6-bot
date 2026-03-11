# Performance Roadmap

This note summarizes the measured runtime bottlenecks, the optimizations that have
already paid off, and the most promising next refactors for larger speedups.

## Current Best Measured Fast Lane

- Baseline tracked smoke:
  - `artifacts/bootstrap_fast_tracked_smoke/metrics.json`
  - total: `254.938s`
  - self-play: `246.498s`
- Current best fast smoke:
  - `artifacts/bootstrap_fast_replycache_smoke/metrics.json`
  - total: `146.468s`
  - self-play: `142.552s`

Net improvement so far:

- total runtime: about `42.5%` faster
- self-play runtime: about `42.2%` faster

## What Already Helped

### 1. Candidate-generation caching and tighter window scanning

Files:

- `src/hex6/prototype/candidate_explorer.py`
- `src/hex6/config/schema.py`
- `src/hex6/game/state.py`

Wins:

- cached analysis scopes, frontier expansions, and bounded-board helpers
- reduced repeated window summarization work
- cached immutable state facts such as signatures and occupied bounds

### 2. Reply-search scalar caching

File:

- `src/hex6/search/baseline.py`

Win:

- cached `worst_reply_score`
- cached `_best_followup_score`
- early exit when the search hits terminal-value ceilings/floors

Measured delta over the previous best fast smoke:

- `173.198s -> 146.468s`
- about `15.4%` faster total

## Current Bottleneck

The engine is still mostly dominated by search-side Python work, not SGD.

Main hotspot area:

- `src/hex6/search/baseline.py`
  - `enumerate_turns`
  - `top_candidates`
  - `worst_reply_score`

The broader runtime picture is still:

- candidate generation
- repeated child-state evaluation
- factorized turn enumeration
- reply-aware shallow search

GPU usage remains modest because the neural net is not the dominant cost on the
fast lane.

## Best Large Refactor Candidates

These are ranked by expected speedup upside, not ease.

### 1. Stop copying full move history during internal search

Most internal search states do not need the full `move_history` tuple, but every
`GameState.apply_placement()` currently appends a new `MoveRecord`.

Why it matters:

- this affects every simulated child state
- tuple growth is pure overhead for internal search
- only a small amount of that history is needed for features such as the last move

Best shape of the change:

- preserve public `move_history` for real game states
- give internal search transitions a cheaper path
- store explicit `last_move` instead of forcing full history copies when search only
  needs recency features

Expected upside:

- high

Risk:

- medium-high because it touches game state, encoder assumptions, and web/gameplay paths

### 2. Dense bounded-board representation for search features

The default game is bounded `15x15`, but much of the search code still behaves like
generic sparse-board Python set/dict logic.

Why it matters:

- `15x15` is tiny enough to support fixed-size arrays or bitboards comfortably
- repeated window counting and candidate scoring could be incremental and cache-friendly
- this is the clearest path to a step change in heuristic-search throughput

Best shape of the change:

- keep sparse external game semantics if desired
- add a dense bounded-board search view for candidate scoring and open-window features
- precompute all legal windows and incidence maps once

Expected upside:

- very high

Risk:

- high because it is a real search-subsystem refactor

### 3. Incremental window-feature updates instead of recomputation

Right now window statistics are still recomputed from the board state for many child nodes.

Why it matters:

- each placement only changes a small local set of windows
- bounded-board line windows can be pre-indexed by cell
- per-move delta updates should beat repeated full rescans

Best shape of the change:

- precompute `cell -> affected windows`
- update open-window counts / best-alignment counts incrementally after each placement
- use those updates inside candidate generation and heuristic scoring

Expected upside:

- high

Risk:

- medium-high

### 4. Monte-Carlo Graph Search / stronger transposition sharing

Current MCTS already has a transposition table toggle, but the engine is still structurally
closer to a tree than a search graph.

Why it matters:

- repeated states across factorized turn search can reuse more information
- graph search can reduce both duplicate expansion work and memory churn

Expected upside:

- medium-high

Risk:

- high

Relevant literature:

- Monte-Carlo Graph Search for AlphaZero: `https://arxiv.org/abs/2012.11045`

### 5. More aggressive batched MCTS / shared inference queues

This matters more for the Colab lane than the fast local lane.

Why it matters:

- batched inference is measurably better than one-state-at-a-time evaluation
- sharing larger batches across more active games is the cleanest way to get more value
  from stronger Colab GPUs

Expected upside:

- medium on local
- higher on Colab

Risk:

- medium-high

Relevant literature:

- Batch Monte Carlo Tree Search: `https://arxiv.org/abs/2104.04278`

### 6. Gumbel-style root control

This is more of a strength-per-simulation upgrade than a raw runtime upgrade, but it can
improve effective efficiency.

Why it matters:

- root action quality matters a lot under limited simulations
- it can improve strength without requiring a proportional increase in simulation count

Expected upside:

- medium on raw runtime
- high on strength per wall-clock hour

Risk:

- medium-high

Relevant literature:

- Gumbel AlphaZero: `https://openreview.net/forum?id=bERaNdoegnO`

## Colab GPU Policy

Google’s Colab FAQ says GPU types vary over time and premium GPUs are subject to availability:

- `https://research.google.com/colaboratory/faq.html`

Current practical policy:

- routine long runs: `V100+`
- strongest-model pushes: `A100` only
- avoid spending long jobs on `T4` unless availability matters more than speed

Important caveat:

- the engine is still substantially search/Python-bound, so faster GPUs do not translate
  into proportional end-to-end speedups yet

## Recommended Next Step

If the goal is the next major runtime step, the best engineering target is:

1. introduce a cheap internal search-state path that avoids copying full move history
2. if that is still not enough, move the bounded-board search features onto a dense
   representation with incremental window updates
