# Day 47 changelog — InstaTrust

## Finding

Two instances of the same mistake, one worse than the other:

- `learn()` re-pulled and re-scanned every instant-lane decision+outcome
  the system had ever logged, on every call — the standard full-rescan
  pattern (Guide 5's Mistake 5).
- `dealer_status(dealer_id)` did the same thing per dealer, and it's called
  from **inside `decide()`** — i.e. on every single instant-lane applicant,
  not just on feedback. This was the hottest full-rescan instance found in
  the whole portfolio.

## Changes

- `gen4/memory.py`, `gen4/feedback.py` — kernel fix (see LendFair's
  changelog for the shared-kernel details): `fact_history`,
  `decisions(outcome_since=...)`, the `outcome_ts` fix, the
  `(system, ts DESC)` index, and the `new_rows_since` / `mark_processed` /
  `accumulate` primitives.

- `service.py`
  - `learn()` rewritten (`LEARN_KEY = "instatrust_learn"`,
    `LEARN_GRACE_DAYS = 7` — justified by `seed.py`'s 90-day outcome lag):
    pulls only instant-lane outcomes since the last watermark, merges
    lane-wide bad/total deltas into a running total via `accumulate()`, and
    also merges per-dealer deltas into `accum:{LEARN_KEY}:dealer:{id}`.
  - `dealer_status()` rewritten to read the per-dealer running total instead
    of re-scanning every decision for that dealer. Safe because
    `record_outcome()` always calls `learn()` before the next `decide()` can
    run for that dealer, so the accumulated total is never stale by the time
    it's read.
  - Caught during implementation: `learn()`'s returned `dealers` dict is
    meant to be a full snapshot of every dealer ever seen (seed.py calls
    `learn()` once at the end and expects this), but `record_outcome()`
    already calls `learn()` internally for every outcome — so by the time an
    explicit final `learn()` call runs, the incremental batch is often
    empty, and a dealer set built from "dealers touched in this batch" would
    wrongly report nothing. Fixed by persisting the dealer set itself
    (`accum:{LEARN_KEY}:known_dealers`) incrementally, so the snapshot always
    covers every dealer that has ever appeared, not just the latest batch.

- `tests/test_incremental_learning.py` — new, 4 tests: `learn()` idempotency,
  picking up new outcomes, `dealer_status()` reading the running total
  correctly (including a never-seen dealer reporting `insufficient_data`
  rather than exploding), and the full-dealer-snapshot behavior across calls.

## Verification

- `pytest -q` → 21/21 passed (17 original + 4 new).
- `run_evals.py` → GATE PASS, 100%/100%, unchanged.
- `seed.py --reset` → identical to pre-fix baseline, including the exact
  per-dealer status dict (`D-13: TRIPPED`, all other 19 dealers `watch`).
  This caught a real regression during implementation (the dealer-snapshot
  bug above) before it shipped — the first version of the fix produced
  `dealers not ok: {}` instead of the correct 20-dealer breakdown.
- `simulate_learning.py` → identical output to pre-fix baseline (v1 vs v2
  instant-lane comparison, D-13 fraud-ring detection, minutes-saved figures).

No behavioral change in the final output — this is a performance /
scalability fix, verified bit-for-bit against the pre-fix baseline.
