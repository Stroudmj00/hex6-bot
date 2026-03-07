# 5-Hour Sprint Plan

## Objective

In the next `5` hours, aim to produce the strongest *validated baseline* we can, not a final
"best possible" bot. The success condition is:

- a correct sparse game engine,
- a measurable search baseline,
- a first configurable training pipeline,
- at least one trained model checkpoint,
- and evaluation results that tell us what to improve next.

## Working principle

This sprint should run as a short feedback loop, not as a long uninterrupted build. The loop
is:

1. Choose the next smallest high-value objective.
2. Implement it in a modular way.
3. Run tests or benchmarks immediately.
4. Report results and ask the next decision question.
5. Adjust the plan using the new evidence.

## Cadence

Use a checkpoint every `20-30` minutes.

At each checkpoint:

- summarize what changed,
- report one or two concrete metrics,
- name the next constraint or uncertainty,
- ask at most one decision question if needed.

If a task is taking longer than `30` minutes without working output, cut scope and ship a
smaller version.

## Execution plan

### Hour 0 to 1: Lock the engine and experiment surface

Deliverables:

- finalize the exact rules and assumptions in config,
- implement sparse board state,
- implement legal move application for `1` opening stone and `2` stones per later turn,
- implement win detection for `6 in a row`,
- implement deterministic test coverage for geometry and terminal states.

Feedback questions:

- Are we keeping the board logically infinite?
- Do we permit any two empty cells on a turn, or any ordering constraints?
- Do we want a finite analysis crop only for models, not for legality?

Exit criteria:

- engine tests pass,
- core rules are no longer ambiguous.

### Hour 1 to 2: Build a strong search baseline before ML

Deliverables:

- implement live-cell and dead-cell analysis,
- implement candidate generation with local, line-extension, blocking, and island modes,
- implement a first tactical evaluator,
- implement a search baseline that can choose moves under a time budget.

Preferred baseline order:

1. threat-driven move scoring,
2. shallow alpha-beta or beam search over factorized two-stone turns,
3. only then guided MCTS if branching factor is under control.

Feedback questions:

- Is the candidate count low enough to search?
- Are island proposals appearing only when structurally justified?

Exit criteria:

- the bot can play complete games,
- we can measure branching factor and move latency.

### Hour 2 to 3: Add the first trainable model interface

Deliverables:

- choose tensor encoding for the sparse board,
- implement dataset generation from search/self-play traces,
- implement a compact policy/value model interface,
- wire config-driven training settings.

Preferred model target:

- factorized policy head:
  first stone distribution, then second stone distribution conditioned on the first,
- plus value head.

Fallback if time is tight:

- train only a value head or a first-stone policy head first.

Feedback questions:

- Do we train on CPU first for correctness, then switch to GPU?
- Is the factorized action representation stable enough for the first run?

Exit criteria:

- one training epoch can run end-to-end,
- samples can be generated automatically.

### Hour 3 to 4: Train and benchmark the first model

Deliverables:

- create a small supervised bootstrap dataset from the search baseline,
- train a compact first model in the `.venv`,
- save checkpoints and training metrics,
- test inference speed and batch behavior.

Feedback questions:

- Is the model helping search enough to justify the extra complexity?
- Is GPU setup working, or do we need to pin the sprint to CPU and postpone CUDA setup?

Exit criteria:

- at least one model checkpoint exists,
- the model is evaluated against a simpler baseline.

### Hour 4 to 5: Evaluation and next-step prioritization

Deliverables:

- run arena games between baseline variants,
- report win rate, speed, and failure modes,
- identify the next bottleneck,
- decide whether the next iteration should focus on search, features, or training volume.

Feedback questions:

- Is the current weakness tactical, strategic, or purely computational?
- What is the highest-leverage next experiment?

Exit criteria:

- sprint results are written down,
- the next iteration plan is evidence-based.

## Responsiveness protocol

To keep the project moving, use this response policy during the sprint:

- Do not queue multiple major unknowns at once.
- Ask questions only when they change architecture, legality, or training format.
- When a reasonable default exists, use it and document it.
- Prefer working output over elegant but untested abstractions.
- Keep assumptions in config so they can be changed without rewrites.

## Decision gates

These are the only decisions that should be allowed to block progress:

- exact game legality and turn structure,
- action representation for two-stone turns,
- GPU environment readiness,
- whether candidate pruning is accurate enough for search.

Everything else should proceed with a default and be revisited later.

## Risks

### Highest risk

The phrase "best model within 5 hours" is too ambitious if interpreted literally. The real
goal should be "best validated baseline we can build in 5 hours."

### Technical risks

- branching factor may still be too high for naive MCTS,
- GPU package setup may consume time,
- factorized two-stone policy design may need one revision,
- long-range island detection may be too weak or too noisy at first.

## What to optimize for

During this sprint, optimize for:

- correctness first,
- measurement second,
- speed third,
- model sophistication fourth.

That order gives the highest chance of ending the session with a bot that actually works and
teaches us something.

