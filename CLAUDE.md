# CLAUDE.md

Project instructions for Claude Code. Read this before touching anything.

## What this is

A procedural state machine that replays real legislative action histories and
proves each transition was legal under the jurisdiction's rules at the time it
happened. Oregon 2025 is the reference corpus: 27,488 action rows, 3,466
measures, currently 100% replay.

The product is not the state machine. The product is the **evidence record** —
a replayable, hash-stamped proof that a measure could only have moved the way
it did. Anything that weakens that claim is a regression even if tests pass.

## Run this before and after every change

```bash
python scripts/check.py
```

Exit 0 or the change does not get committed. It enforces two invariants that
pull against each other:

- **Coverage** (currently 100%) — every measure still replays.
- **Adjacent-swap rejection** (currently ~35% with derived flows, floor 14%) —
  the schema still refuses scrambled histories.

Either number alone is gameable. A validator that accepts everything scores
100% coverage. A validator that accepts nothing scores 100% rejection. Both
must hold.

## The development loop

1. `python scripts/bulk_replay.py 2025R1` — read the **top** halt reason.
2. Add or fix **one** rule in `replay_harness.py`.
3. `python scripts/check.py` — if coverage dropped, the rule is greedy and is
   eating a real transition out of a longer row. Revert, narrow, retry.
4. Repeat. One rule per iteration. Do not batch fixes; you lose the attribution
   that tells you which change caused the regression.

## Hard rules

- **Stdlib only.** No pip installs, no requirements.txt. If a change needs a
  dependency, stop and say so instead of adding it.
- **Never widen `CHAMBER_FLOW` to make a bill pass.** If a transition is
  blocked, first prove the mapping produced the right state. Widening the graph
  to fix a mapping bug raises coverage and silently destroys the false-accept
  number, which is the whole point.
- **Never split action text on sentence boundaries.** Legal citations
  ("Art. V, sec. 15b") and legislator initials ("Carried by Smith G.") are full
  of periods. Matching is span-based over the full row: longest-match-wins on
  overlap, emits ordered by start offset, each carrying `(rule_id, start, end)`.
- **Fail closed.** Unrecognized action text halts the replay. Never degrade it
  into a payload note — a silent pass-through puts holes in the audit trail
  with no signal that they exist.
- **Do not regenerate `schemas/*_chamber_flows.py` from a run that did not hit
  100%.** You will bake a truncated graph into the constraint.
- **Merge, never overwrite, when adding a session.** A second session surfaces
  edges the first never used; dropping the first session's edges discards
  procedure it proved legal.
- Commit directly to `develop`. No PRs, no new branches. Ask before any
  destructive operation.

## Constraints the data forced (do not re-derive these)

- A row is a **sequence** of events, not one. "Rules suspended. Third reading.
  Carried by Nash. Passed." is four.
- A measure has a state **in each chamber**, not one global state. A single
  state field makes second-chamber first reading illegal after origin passage.
- A failed **motion** is not a failed **measure**. "Motion to substitute
  Minority Report ... failed" must not set the measure to `failed`.
- `vetoed` is **not terminal**. SB 875 (2025): vetoed 06-24, Senate repassed
  over the veto 06-25, House tabled 06-26, veto sustained 06-27.
- Resolutions are a **second grammar** — `Do adopt` / `Final reading` /
  `Adopted`. They never touch the pass/enact vocabulary.
- `ActionDate` is the only defensible sort key. `MeasureHistoryId` contradicts
  it (id 654676 @ 08:33 precedes 654677 @ 08:32 in SB976).
- `ActionDate` vs `CreatedDate` is occurred_at vs recorded_at, and rows carry a
  mutable `ModifiedDate`. This is why a transition must stamp the schema hash it
  was validated against rather than recompute from the calendar at replay time.
- Rules suspension is **not** required for passage — 78 of 1,334 passage rows.
- The **House** sends bills to the governor too — 351 "Governor signed" rows in
  H vs 282 in S. Never hard-code the executive path to one chamber.

## Layout

```
replay_harness.py                 mapping table (79 rules) + schema + validator
schemas/or_legislature_v2.yaml    effective-dated Oregon pack, partly unverified
scripts/fetch_session.py          paginated download -> cache/
scripts/bulk_replay.py            coverage + ranked halts + uncovered fragments
scripts/perturbation_test.py      false-accept measurement
scripts/derive_chamber_flows.py   learn per-chamber graphs from the corpus
scripts/check.py                  the gate — run before every commit
```

## Queued task

Run the rule set against a session it has never seen:

```bash
python scripts/fetch_session.py 2023R1
python scripts/bulk_replay.py 2023R1
```

Report the completion percentage and the ranked halts **before** fixing
anything. That first number is the finding: if 2023 replays at 95%+ with a
dozen additions, this encodes Oregon procedure. If it needs 40+ new rules, it
encodes 2025 clerical style, and the per-session maintenance cost is the
project's real risk. Do not tune toward a better number before reporting the
untuned one.
