# Project Memory

This file records persistent project assumptions and operator constraints so the repo keeps
the working context.

## Interaction expectations

- The website must allow direct hex selection with pointer input.
- The board must support drag-to-pan across an effectively infinite grid.
- The board should not render coordinate labels in the play view.
- The first played stone should be treated as the display origin for the session.

## Representation expectations

- The legal game remains a sparse, effectively infinite board.
- For learning and dataset generation, positions should be translation-normalized so the
  first played stone becomes `(0, 0)` when practical.
- Key search, training, and pruning assumptions belong in config files rather than being
  hard-coded into the engine.

## Colab integration boundary

- Google Colab is a separate runtime, not a hidden extension of the local shell.
- Coordination must happen through explicit commits, notebook code, Drive artifacts, logs,
  and saved checkpoints.
- The primary live-status bridge is now the `colab-status` GitHub branch with machine-written
  JSON status files.
- Heavy recurring training/eval should run in Colab when practical; the local machine should
  default to `watch_status` plus the play website.
- If tighter integration is needed later, it must be implemented as an explicit bridge,
  not assumed.

## Delivery strategy

- Start with small, fast profiles to validate correctness and wiring.
- Scale candidate widths, training volume, and model size only after the small path is
  working and measured.
- End-state goal for the sprint is a playable website against the current bot, with Colab
  available for heavier training runs.
- The current measurement path is bootstrap training plus arena Elo tracking after each
  cycle; full model-guided self-play is a later upgrade.
