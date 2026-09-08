"""Replay an entire cached session offline. This is the coverage number.

    python scripts/fetch_session.py 2025R1
    python scripts/bulk_replay.py 2025R1

Prints: completion %, ranked halt reasons (with an example measure for each),
ranked uncovered text fragments, and the distribution of final states.

Workflow: read the top halt reason, add or fix one rule in replay_harness.py,
rerun. Completion must never go down. If it does, the rule you added is greedy
and is eating a real transition out of a longer row.
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import replay_harness as h  # noqa: E402

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")


def load(session):
    path = os.path.join(CACHE, f"{session}.json")
    if not os.path.exists(path):
        sys.exit(f"no cache for {session} — run: python scripts/fetch_session.py {session}")
    rows = json.load(open(path))
    by = collections.defaultdict(list)
    for r in rows:
        by[f"{r['MeasurePrefix']}{r['MeasureNumber']}"].append(r)
    # ActionDate is the only defensible sort key; MeasureHistoryId contradicts it
    for k in by:
        by[k].sort(key=lambda r: (r["ActionDate"], r["MeasureHistoryId"]))
    return rows, by


def main(session):
    rows, by = load(session)
    print(f"{session}: {len(rows)} rows, {len(by)} measures\n")

    completed, halts, uncovered, finals, examples = 0, collections.Counter(), \
        collections.Counter(), collections.Counter(), {}
    for mid, mrows in by.items():
        item, halt, gaps = h.replay(mid, mrows)
        uncovered.update(g for g in gaps if len(g) > 3)
        if halt:
            key = halt.split("  [")[0]
            halts[key] += 1
            examples.setdefault(key, (mid, halt))
        else:
            completed += 1
            finals[tuple(sorted(item.states.items()))] += 1

    total = len(by)
    print(f"COMPLETION: {completed}/{total} = {100*completed/total:.1f}%\n")
    print("--- halt reasons (fix these top-down) ---")
    for reason, n in halts.most_common(20):
        mid, full = examples[reason]
        print(f"{n:5}  {reason}")
        print(f"       eg {mid}: {full[:120]}")
    print("\n--- uncovered text fragments (candidate rules) ---")
    for frag, n in uncovered.most_common(25):
        print(f"{n:5}  {frag[:78]}")
    print("\n--- final states ---")
    for st, n in finals.most_common(10):
        print(f"{n:5}  {dict(st)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "2025R1")
