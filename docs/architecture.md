# Architecture

## Design principles

- Config-first: assumptions live in `TOML`, not scattered constants.
- Sparse-first: the board is stored sparsely even though the default game is a bounded `15 x 15` board.
- Modular package boundaries: game logic, search, training, and evaluation should remain
  separable.
- Importable prototypes: exploratory code should still live in modules, not throwaway
  notebooks.

## Package outline

### `src/hex6/config`

- Load typed configuration from `configs/*.toml`.
- Centralize defaults and validation logic.

### `src/hex6/game`

- Coordinate types and geometry helpers.
- Sparse board state.
- Line and window enumeration.
- Terminal-state detection.

### `src/hex6/search`

- Threat detectors.
- Candidate generators.
- Tactical solver.
- Guided MCTS and later search variants.

### `src/hex6/nn`

- Board encoders.
- Policy/value networks.
- Batched inference service.

### `src/hex6/train`

- Self-play workers.
- Replay storage.
- Learner loop.
- Reanalysis and curriculum logic.

### `src/hex6/eval`

- Arena matches.
- Elo tracking.
- Performance and regression benchmarks.

### `src/hex6/prototype`

- Experimental modules that remain importable.
- Used to explore candidate generation, pruning, and feature ideas before they become part
  of the production engine.

## Near-term implementation order

1. Config loader and schema.
2. Coordinate and sparse-board primitives.
3. Window analysis and dead/live cell detection.
4. Prototype candidate explorer.
5. Engine tests.
6. Search baseline.
7. Neural components.
