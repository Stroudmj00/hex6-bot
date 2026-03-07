# Game Exploration

## Working ruleset

The current target is the `6 in a row` hexagonal variant described in the linked video:

- The board is treated as effectively infinite.
- `X` places `1` opening stone.
- After that, each player places `2` stones per turn.
- A player wins by making `6` contiguous stones in a straight line on any of the three
  hex-grid axes.

These rules are still stored in config so we can change them later without refactoring the
 codebase.

## Representation decision

For learning and dataset generation, positions should be translation-normalized so that the
first played stone becomes `(0, 0)`.

This should be treated as a representation choice, not a rule change:

- the legal game remains an infinite sparse board,
- the engine may still store absolute coordinates internally,
- but training data, hashing, and model inputs should use a canonical translated frame when
  practical.

The website now follows this display convention by treating the first played stone as the
session origin.

## Why this game is hard

- A two-stone turn explodes the action space.
- Strong moves are not always purely local.
- The game appears to be driven by threat sequences and momentum.
- Some strategically strong moves may create a second attack region several cells away.

This means the project should not assume:

- a fixed board,
- a purely local search frontier,
- or naive full-width MCTS over all empty cells.

## Core concepts to model

### 6-window

A `6-window` is any contiguous line of `6` cells on one of the three hex axes.

### Open window

For player `P`, a `6-window` is open if it contains no opponent stones.

### Live cell

A cell is live for player `P` if it belongs to at least one open `6-window` for `P`.

### Globally dead cell

A cell is globally dead if it belongs to no open `6-window` for either player. This is a
safe candidate-generation prune, though it should not remove the cell from stored board
state.

### Threat strength

Threats should eventually be classified by both:

- how many placements are needed to complete a win,
- and how many blocking stones the opponent needs to fully neutralize the line.

### Momentum

Momentum is the practical observation that one side can force repeated defensive replies by
creating successive threats.

### Island candidate

An island candidate is a nonlocal move or move-pair that is not strongest because it is
adjacent to current stones, but because it sits inside several promising future windows with
room to grow into a separate attack region.

## Candidate-generation direction

The current prototype should combine several candidate sources:

- Local tactical frontier near existing stones.
- Line-extension cells for existing friendly or enemy alignments.
- Blocking cells for urgent opponent threats.
- Long-range island seeds that score well by open-window geometry rather than by distance
  alone.

## Open research questions

- How often do strong second-island moves occur in serious play?
- Is the best action abstraction a pair of stones, or first-stone then conditional
  second-stone?
- How reliable is globally dead-cell pruning once the board becomes large and noisy?
- Can a compact policy/value net learn to propose nonlocal strategic seeds early enough to
  reduce search cost?
