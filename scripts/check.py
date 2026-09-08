"""Verification gate. Exit 0 = the change is safe. Exit 1 = revert it.

    python scripts/check.py            # 2025R1, default thresholds
    python scripts/check.py 2025R1 100 30

Enforces the two invariants that make this project meaningful:

  1. COVERAGE must not regress. Every measure in the baseline session must
     still replay. A dropped measure means a rule you added is greedy and is
     swallowing a real transition out of a longer row.

  2. FALSE-ACCEPT must not regress. Adjacent-swap rejection must stay at or
     above the recorded floor. If coverage held but swap rejection fell, you
     widened the transition graph to paper over a mapping bug. Fix the rule
     instead of the graph.

Both must pass. Either one alone is gameable: a validator that accepts
everything scores 100% coverage, and a validator that accepts nothing scores
100% rejection.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# recorded floors — raise these when you legitimately improve, never lower them
COVERAGE_FLOOR = 100.0      # percent of measures that must replay
SWAP_FLOOR = 14.0           # percent of adjacent-swapped histories rejected
SAMPLE = 400


def main(session="2025R1"):
    import collections
    import random
    import replay_harness as h
    from scripts.bulk_replay import load

    _, by = load(session)

    completed, halts = 0, collections.Counter()
    for mid, mrows in by.items():
        _item, halt, _gaps = h.replay(mid, mrows)
        if halt:
            halts[halt.split("  [")[0]] += 1
        else:
            completed += 1
    coverage = 100 * completed / len(by)

    random.seed(7)
    cands = [(k, v) for k, v in by.items() if len(v) >= 8]
    sample = random.sample(cands, min(SAMPLE, len(cands)))
    real_rejected = swapped = 0
    for _k, v in sample:
        if h.replay("x", v)[1] is not None:
            real_rejected += 1
        i = random.randrange(len(v) - 1)
        q = v[:]
        q[i], q[i + 1] = q[i + 1], q[i]
        if h.replay("x", q)[1] is not None:
            swapped += 1
    swap_pct = 100 * swapped / len(sample)

    ok = True
    print(f"session {session}: {len(by)} measures\n")
    for label, value, floor, cmp_ in [
        ("coverage", coverage, COVERAGE_FLOOR, ">="),
        ("adjacent-swap rejection", swap_pct, SWAP_FLOOR, ">="),
    ]:
        passed = value >= floor
        ok &= passed
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}: {value:.1f}% (floor {floor}%)")
    if real_rejected:
        ok = False
        print(f"  [FAIL] {real_rejected} real histories rejected — must be 0")

    if halts:
        print("\n  top halts:")
        for reason, n in halts.most_common(5):
            print(f"    {n:5}  {reason[:88]}")

    print("\n" + ("OK" if ok else "REGRESSION — revert or fix before committing"))
    return 0 if ok else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) >= 2:
        COVERAGE_FLOOR = float(args[1])
    if len(args) >= 3:
        SWAP_FLOOR = float(args[2])
    sys.exit(main(args[0] if args else "2025R1"))
