# Engine Comparison: Hex6 vs Cloudict vs Carbon

## Goal

Document ideas in external engines that are missing from this repository and identify which implementation style is currently superior for performance.

External engines inspected:

- `tmp_cloudict` (Connect6 engine)
- `tmp_carbon` (Gomoku engine)

## Executive Verdict

For raw tactical search performance, both external engines are ahead of the current in-repo `BaselineTurnSearch`.

- Best search infrastructure: `Carbon` (iterative deepening + transposition table + strong move ordering).
- Best dedicated tactical forcing solver: `Cloudict` (explicit VCF + anti-VCF pipeline).
- Best architectural flexibility: current `Hex6` (config-first + sparse infinite board), but that flexibility currently trades off immediate tactical strength.

Pragmatic conclusion:

- If the objective is strongest near-term tactical performance, Carbon-style search infrastructure is the best baseline to replicate first.
- If the objective is Connect6-style forced-line tactical solving, Cloudict's VCF stack is the highest-value tactical module to port/adapt.
- Long-term strongest path for this repo is a hybrid: Carbon-like search core plus Cloudict-like threat solver, adapted to Hex6 board/rules.

## Evidence Snapshot

### Current Hex6

- Search is shallow and candidate-factorized, not full recursive minimax:
  - `BaselineTurnSearch` and `choose_turn`: `src/hex6/search/baseline.py:24`, `src/hex6/search/baseline.py:35`
  - Reply sampling in `worst_reply_score`: `src/hex6/search/baseline.py:180`
- Candidate generation is feature-rich but still local/heuristic:
  - `candidate_scores`: `src/hex6/prototype/candidate_explorer.py:207`
  - dead-cell pruning flag path: `src/hex6/prototype/candidate_explorer.py:227`
  - long-range islands flag path: `src/hex6/prototype/candidate_explorer.py:240`
- Model-guided mode re-ranks baseline candidate turns (not deep tree search):
  - `ModelGuidedTurnSearch`: `src/hex6/search/model_guided.py:26`
  - baseline turn enumeration dependency: `src/hex6/search/model_guided.py:69`
- Board/rules are sparse-infinite by design:
  - game-state contract: `src/hex6/game/state.py:30`
- Search schema exposes advanced switches that are not wired into baseline runtime:
  - schema fields: `src/hex6/config/schema.py:55`
  - examples in configs: `configs/default.toml:36`, `configs/play.toml:36`

### Cloudict

- Explicit alpha-beta recursion:
  - declaration: `tmp_cloudict/src/search_engine.h:23`
  - recursion and pruning: `tmp_cloudict/src/search_engine.cc:41`
- Two-stage Connect6 move generation (first stone + second stone widths):
  - width constants: `tmp_cloudict/src/defines.h:44`
  - move generation core: `tmp_cloudict/src/move_generator.cc:59`
- Dedicated VCF/anti-VCF tactical solver:
  - interfaces: `tmp_cloudict/src/vcf_search.h:64`
  - recursive VCF and anti-VCF implementations: `tmp_cloudict/src/vcf_search.cc:747`, `tmp_cloudict/src/vcf_search.cc:914`
- Search pipeline uses VCF first, then alpha-beta:
  - `search_a_move`: `tmp_cloudict/src/game_engine.cc:189`
  - VCF-first call path: `tmp_cloudict/src/game_engine.cc:194`
  - alpha-beta fallback: `tmp_cloudict/src/game_engine.cc:213`
- Fixed 19x19+borders board assumptions:
  - `GRID_NUM 21`: `tmp_cloudict/src/defines.h:26`
  - board comment in engine: `tmp_cloudict/src/game_engine.h:32`

### Carbon

- Minimax/alpha-beta with narrow windows:
  - declaration: `tmp_carbon/AICarbon.h:99`
  - implementation: `tmp_carbon/AICarbon.cpp:317`
- Iterative deepening and time management in move selection:
  - `yourTurn`: `tmp_carbon/AICarbon.cpp:97`
  - iterative loop: `tmp_carbon/AICarbon.cpp:131`
- Active transposition table in search:
  - hash table class: `tmp_carbon/AICarbonHash.h:21`
  - table probe/use in minimax: `tmp_carbon/AICarbon.cpp:388`
  - table update: `tmp_carbon/AICarbon.cpp:421`
- Tactical fast-path forcing logic:
  - `quickWinSearch`: `tmp_carbon/AICarbon.cpp:242`
- Candidate generation and prioritization with TT best-move preference:
  - `generateCand`: `tmp_carbon/AICarbon.cpp:179`
  - TT best-first candidate insertion: `tmp_carbon/AICarbon.cpp:187`

## Feature Matrix

| Capability | Hex6 (current) | Cloudict | Carbon | Performance Winner |
|---|---|---|---|---|
| Deep recursive game-tree search | No (shallow reply sampling) | Yes (alpha-beta) | Yes (minimax/alpha-beta) | Cloudict/Carbon |
| Transposition table in live search | No | Partial in VCF subsystem | Yes, integrated in minimax | Carbon |
| Threat-forcing tactical solver | No dedicated solver | Yes (VCF + anti-VCF) | Yes (quickWinSearch, lighter than full VCF) | Cloudict |
| Iterative deepening with time budget | No | Depth configurable, not same iterative loop | Yes | Carbon |
| Candidate generation sophistication | Moderate/high heuristic features | High, hand-tuned two-stage | High, pattern+priority+threat filters | Cloudict/Carbon |
| Rule/board flexibility | High (sparse infinite) | Low (fixed board assumptions) | Medium/low (fixed max board arrays) | Hex6 |

## Ideas External Engines Have That Hex6 Does Not (Yet)

1. Full alpha-beta search tree with deep recursive cutoffs.
2. Real transposition table integrated into main search loop.
3. Tactical forcing solver equivalent to VCF/anti-VCF.
4. Iterative deepening with hard time-budget behavior.
5. TT-guided move ordering and principal-variation style first-move probing.
6. Aggressive threat-state filtering in candidate generation before deep recursion.

## Current Gap in This Repository

The current runtime path mainly tunes candidate widths and heuristic weights. It does not yet activate algorithmic steps that usually dominate tactical performance.

- draw-heavy matrix evidence: `docs/experiment-report.md:26`
- search matrix currently varies shallow knobs: `configs/experiments/search_matrix.toml:8`

## Superior Implementation for Performance

If we must pick a single superior implementation style to copy first for performance, choose Carbon's search core.

Why:

1. It combines iterative deepening, alpha-beta search, and transposition reuse in one coherent move-selection loop.
2. It is easier to adapt incrementally to this repo than full Cloudict VCF stack.
3. It improves both move quality and latency stability, which matters for interactive play and benchmarking.

Counterpoint:

- Cloudict remains superior for explicit forced-line tactical solving (VCF). After Carbon-style core search is in place, Cloudict-style tactical module should be the next upgrade.

## Recommended Port Order

1. Add Carbon-style iterative deepening + alpha-beta + TT to `hex6.search`.
2. Preserve current candidate explorer as move-ordering input to the new tree search.
3. Add threat-forcing solver inspired by Cloudict VCF once baseline deep search is stable.
4. Extend arena with tactical suites/opening suites to reduce draw saturation before making final Elo claims.

## Benchmark Criteria for Final Confirmation

To convert this directional verdict into a hard measured verdict in this repo:

1. Fixed per-move wall-clock budget.
2. Equal opening suite and side-balancing.
3. Metrics: node count, solved tactical positions, win rate, draw rate, and median move latency.
4. At least one tactical benchmark set (forced-win/forced-defense puzzles), not just whole-game arena.

Until those experiments are run, this document's superiority judgment is implementation-based and architecture-based, not an in-repo Elo proof.

## Implementation Backlog

Actionable, priority-scored tickets for this verdict are tracked in:

- `docs/engine-upgrade-tickets.md`
