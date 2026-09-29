# proc_track

Replays every Oregon legislative bill history from the state's public API and
checks that each step was a legal move under chamber procedure. When a history
can't be explained, the replay halts and says why, instead of guessing.

Python 3.12+, standard library only. No API key. Built and maintained solo.

## What it shows

Public records are messy. Oregon publishes each bill's history as free-text
action rows ("Rules suspended. Third reading. Carried by Nash. Passed.") with
timestamps that contradict the record IDs and fields that can change after
publication. This project turns that into a validated, per-chamber state
history with provenance on every transition, then measures how far the
validation can be trusted.

## Results

Four regular sessions, about 103,000 action rows, 11,723 measures, 120 mapping
rules.

| session | action rows | measures replayed | adjacent-swap rejection | gate |
|---|---|---|---|---|
| 2025R1 | 27,488 | 3,466 / 3,466 | 15.5% | pass |
| 2021R1 | 24,568 | 2,519 / 2,519 | 19.8% | pass |
| 2019R1 | 25,563 | 2,767 / 2,768 | 16.8% | 1 open halt |
| 2023R1 | 25,844 | 2,969 / 2,970 | 12.8% | 1 open halt, swap below floor |

The two open halts are listed under **Known issues**. They are reported rather
than hidden because the point of the tool is that nothing passes silently.

### Why two numbers

Coverage alone proves nothing: a validator that accepts everything scores 100%.
So every run also scrambles real histories and counts how many the schema
refuses. On 2025R1:

- real order rejected: 0 / 400 (must be zero)
- reversed order rejected: 400 / 400
- full shuffle rejected: 397 / 400
- adjacent swap rejected: roughly 15% (the hard case — one swapped pair of
  events is often still legal procedure)

Coverage and rejection pull against each other. Publishing the pair is what
makes the coverage number mean something.

## Run it

```bash
git clone https://github.com/ominous-22/proc_track && cd proc_track
make replay     # coverage + ranked halt reasons, 2025R1 (cached, no network)
make perturb    # false-accept measurement
make check      # the gate: exits nonzero on any regression
make check SESSION=2021R1
```

Session data for all four sessions is cached in `cache/`. To re-pull from the
API: `make fetch SESSION=2025R1` (about 27k rows, six paged requests).

One bill, for tracing a single trajectory:

```bash
python replay_harness.py --session 2025R1 --measures SB976
```

## How it works

1. **Fetch** — page Oregon's OData `MeasureHistoryActions` into a local cache.
2. **Map** — match each action row against 120 regex rules using span offsets
   over the whole row. A row can emit several events. Overlaps resolve
   longest-match-wins, and every emitted event carries `(rule_id, start, end)`
   so any state can be traced back to the exact characters that produced it.
3. **Validate** — step each event through a per-chamber transition graph.
   Unrecognized text or an illegal move halts the replay (fail closed).
4. **Measure** — `bulk_replay` ranks halts and unmatched text fragments;
   `perturbation_test` measures false acceptance; `check` enforces both floors.

## Things the data forced

Each of these was a bug first.

- **Don't split on sentence boundaries.** Citations ("Art. V, sec. 15b") and
  initials ("Carried by Smith G.") are full of periods.
- **A row is a sequence of events, not one event.**
- **A bill has a state in each chamber**, not one global state. Otherwise
  second-chamber first reading looks illegal after origin passage.
- **A failed motion is not a failed bill.** "Motion to substitute Minority
  Report ... failed" must not mark the measure failed.
- **Vetoed is not terminal.** SB 875 (2025) was vetoed, repassed over the veto
  in the Senate, tabled in the House, and the veto sustained, over four days.
- **Sort by `ActionDate`, not record ID.** IDs contradict timestamps (SB 976:
  id 654676 at 08:33 precedes 654677 at 08:32).
- **Records are mutable.** Rows carry a `ModifiedDate`, so a transition should
  stamp the rule set it was validated against rather than be recomputed later.
- **Don't hard-code assumptions from one chamber.** The House sends bills to the
  governor too (351 "Governor signed" rows in the House vs 282 in the Senate),
  and 5.8% of passages happen without a rules suspension.

## Development rule

Read the top halt, change one rule, rerun the gate. If coverage drops, the new
rule is greedy and is swallowing a real transition from a longer row. If
coverage holds but swap rejection drops, the graph was widened to hide a
mapping bug — fix the rule, not the graph.

## Known issues

- **2019R1:** one measure halts on `S: passed -> second_reading`. Two graph edges
  that let it pass were removed on purpose because they only existed for that
  one bill (HB 2998) and weakened rejection everywhere else.
- **2023R1:** one measure halts on an unmapped action ("Rescission of the
  subsequent referral denied by Order of the President"), and adjacent-swap
  rejection sits at 12.8%, under the 14% floor.
- Per-chamber flow graphs are derived for 2023R1 and 2025R1 only.

## Layout

```
replay_harness.py            mapping rules + transition graph + validator
scripts/fetch_session.py     paged session download -> cache/
scripts/bulk_replay.py       coverage, ranked halts, unmatched fragments
scripts/perturbation_test.py false-accept measurement
scripts/derive_chamber_flows.py  derive per-chamber graphs from a clean run
scripts/check.py             regression gate
schemas/                     derived chamber flows + draft Oregon YAML pack
cache/                       four sessions of raw API data
data/                        reference trajectory (SB 976) + action templates
```
