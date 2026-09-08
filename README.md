# proc_track — procedural state machine + replay harness

Validates that legislative measures moved legally through a jurisdiction's
procedure, and measures how confident you're entitled to be about that claim.

Stdlib only. Python 3.12+. No API key, no network egress beyond
`api.oregonlegislature.gov`.

## Setup (Kali)

```bash
cd ~
git init proc_track && cd proc_track   # or drop this tarball here
python3 -m venv .venv && source .venv/bin/activate
python --version                        # 3.12 or 3.13
```

Nothing to install.

## The loop

```bash
# 1. pull a session to ./cache (~27k rows, ~7 MB, 6 paged requests)
python scripts/fetch_session.py 2025R1

# 2. coverage: can every measure replay?
python scripts/bulk_replay.py 2025R1

# 3. false-accept: does the schema refuse scrambled histories?
python scripts/perturbation_test.py 2025R1

# 4. tighten: derive per-chamber graphs from what the corpus actually does
python scripts/derive_chamber_flows.py 2025R1
```

Single measure, for debugging a specific trajectory:

```bash
python replay_harness.py --session 2025R1 --measures SB976
```

## Current numbers (2025R1, 27,488 rows, 3,466 measures)

| metric | value |
|---|---|
| completion | 3466/3466 = 100.0% |
| reversed rejected | 100.0% |
| full shuffle rejected | 99.2% |
| adjacent swap rejected | 35.2% (with derived per-chamber flows; 14.5% with the shared graph) |
| rules | 79 |

Two numbers matter, and they pull against each other. Coverage alone proves
nothing — a validator that accepts everything scores 100%. Publish the pair.

## The development loop

Run `bulk_replay.py`, read the top halt reason, add or fix **one** rule in
`replay_harness.py`, rerun.

- Completion must never go down. If it does, the rule you added is greedy and
  is swallowing a real transition out of a longer row. This happened once
  already: `Special Order of Business[^.]*` ate `Third reading` out of
  "Special Order of Business, Third reading. Passed."
- Then rerun `perturbation_test.py`. If completion held and adjacent-swap
  rejection rose, the change was real tightening. If swap rejection fell, you
  widened the graph to paper over a mapping bug — fix the rule instead.

## Design decisions that were expensive to learn

- **Never split action text on sentence boundaries.** Legal citations
  ("Art. V, sec. 15b") and legislator initials ("Carried by Smith G.") are full
  of periods. Match with span offsets over the whole row instead; overlaps
  resolve longest-match-wins, emits are ordered by start offset, and every
  transition carries `(rule_id, start, end)` for provenance.
- **A row is a sequence of events, not one event.** "Rules suspended. Third
  reading. Carried by Nash. Passed." is four.
- **A measure has a state in each chamber, not one global state.** A single
  state field makes second-chamber first reading illegal after origin passage.
- **A failed *motion* is not a failed *measure*.** "Motion to substitute
  Minority Report ... failed" must not set the measure to `failed`.
- **`vetoed` is not terminal.** SB 875 (2025): vetoed 06-24, Senate repassed
  over the veto 06-25, House tabled 06-26, veto sustained 06-27. The override
  succeeded in one chamber and died in the other.
- **Resolutions are a second grammar.** `Do adopt` / `Final reading` /
  `Adopted` — they never touch the pass/enact vocabulary.
- **`ActionDate` is the only defensible sort key.** `MeasureHistoryId` order
  contradicts it (id 654676 @ 08:33 precedes 654677 @ 08:32 in SB976).
- **`ActionDate` vs `CreatedDate` is occurred_at vs recorded_at**, and rows
  carry a `ModifiedDate` — upstream records are mutable after publication.
  That's why a transition must stamp the schema hash it was validated against
  rather than recompute from the calendar at replay time.
- **Rules suspension is not required for passage** — 78 of 1,334 passage rows
  (5.8%). Don't gate the passage edge on it.
- **The House sends bills to the governor too** — 351 "Governor signed" rows in
  H vs 282 in S. Don't hard-code the executive path to one chamber.

## Claude Code

The repo ships a `CLAUDE.md` with the invariants, the hard rules, and the queued
task. `scripts/check.py` is the gate — it exits nonzero on a coverage or
false-accept regression, so an agent can verify its own edits without asking.

## Contents

```
replay_harness.py                    mapping table + schema + validator (79 rules)
schemas/or_legislature_v2.yaml       effective-dated Oregon pack (hand-written, partly unverified)
scripts/fetch_session.py             paginated session download -> cache/
scripts/bulk_replay.py               coverage + ranked halts + uncovered fragments
scripts/perturbation_test.py         false-accept measurement
scripts/derive_chamber_flows.py      learn per-chamber graphs from the corpus
data/sb976_trajectory.json           SB 976 (2025R1) — the vetoed reference bill
data/or2025r1_action_templates.csv   368 action templates ranked by frequency
cache/2025R1.json                    pre-seeded, delete to re-fetch
```

## Next

Run against a second session (`2023R1`, `2024R1`). The rule set has only ever
seen 2025. If 2023 replays at 95%+ with a dozen additions, this is Oregon
procedure. If it needs 40 new rules, it's 2025 clerical style, and the
per-session maintenance cost is the real product risk.
