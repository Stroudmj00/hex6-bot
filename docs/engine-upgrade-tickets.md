# Engine Upgrade Tickets

## Goal

Turn the Hex6 vs Cloudict vs Carbon comparison into an executable, prioritized
implementation backlog that is connected to the Colab runtime loop.

## Priority Tickets

| Ticket | Priority | Scope | Success Criteria | Colab Validation Job |
|---|---:|---|---|---|
| `ENG-001` Carbon-style search core | 100 | Add iterative deepening + alpha-beta + TT in `hex6.search` | New search path is selectable by config; tactical win-rate and node-efficiency improve at equal time budget | `cycle_main` + `tournament_regression` |
| `ENG-002` Cloudict-style forcing solver | 80 | Add dedicated forced-line threat solver (VCF/anti-VCF-inspired) | Forced-win and forced-defense suite solve-rate improves without severe latency regressions | `tournament_regression` + tactical suite job |
| `ENG-003` Benchmark harness upgrade | 70 | Add fixed time-budget arena and tactical suites with timestamps and trend output | Reports include node counts, draw rates, latency medians, solved tactical positions over time | `search_matrix_regression` + tournament |
| `ENG-004` Candidate-ordering integration | 60 | Reuse candidate explorer features as move ordering for deep search | Better pruning efficiency at equal move quality | `search_matrix_regression` |
| `ENG-005` Draw-saturation mitigation | 50 | Opening suite and side-balancing in eval loop | Draw rate drops enough to separate variants in Elo trends | `tournament_regression` (`max_game_plies=100`) |

## Colab Connection

Queue config:

- `configs/colab_job_queue.toml`

Runner command:

```bash
python -m hex6.integration.run_priority_loop --queue configs/colab_job_queue.toml --state artifacts/colab_queue/state.json --status-backend github_branch
```

The notebook supports this directly with:

- `RUN_MODE = "priority_loop"` in `notebooks/hex6_colab_fast_bootstrap.ipynb`

## Notes

- Priorities are explicit numeric scores; higher score runs first when eligible.
- `min_interval_minutes` gates each job to avoid over-sampling one lane.
- `max_consecutive_runs` avoids starvation (for example, `cycle_main` can yield
  after a short streak so evaluation jobs still run).
- This queue keeps a single Colab runtime busy while it remains connected; it
  does not bypass Colab runtime lifetime limits.
