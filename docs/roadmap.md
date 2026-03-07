# Roadmap

## Stage 0: Research scaffold

- Create the package layout.
- Put assumptions in config files.
- Define terminology and open questions.
- Build an importable prototype for move-candidate exploration.

## Stage 1: Engine core

- Implement sparse board state and move application.
- Add exact terminal detection for `6 in a row`.
- Add active-region and window enumeration utilities.
- Add tests for geometry and win detection.

## Stage 2: Search baseline

- Implement tactical threat analysis.
- Implement candidate generation with local, blocking, line-extension, and island modes.
- Build a strong non-neural baseline before introducing GPU inference.

## Stage 3: Guided neural search

- Add a compact policy/value network.
- Batch GPU inference across many search requests.
- Compare tactical search, guided MCTS, and hybrid variants.

## Stage 4: Training and evaluation

- Bootstrap from search-generated data.
- Move into self-play.
- Track Elo, speed, branching factor, and memory use.

