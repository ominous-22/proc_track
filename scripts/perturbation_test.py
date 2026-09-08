"""False-accept measurement. Coverage alone is meaningless — a validator that
accepts everything replays 100%. This scrambles real histories and reports how
many the schema refuses.

    python scripts/perturbation_test.py 2025R1 [sample_size]

Four numbers:
  real order rejected      must be 0.0%   (any rejection is a coverage bug)
  reversed rejected        should be ~100%
  full shuffle rejected    should be ~99%
  adjacent swap rejected   the one that actually moves — tighten to raise it

Bills that die in committee have order-insensitive histories (referral, hearing,
work session, repeat), so adjacent-swap rejection has a hard ceiling well under
100%. About two thirds of Oregon measures are that shape.
"""
import collections
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import replay_harness as h  # noqa: E402
from scripts.bulk_replay import load  # noqa: E402

MIN_ACTIONS = 8


def halts(rows):
    return h.replay("perturbed", rows)[1] is not None


def main(session, sample_size=400, seed=7):
    _, by = load(session)
    random.seed(seed)
    cands = [(k, v) for k, v in by.items() if len(v) >= MIN_ACTIONS]
    sample = random.sample(cands, min(sample_size, len(cands)))

    real = shuffled = reversed_ = swapped = 0
    survivors = []
    for k, v in sample:
        if halts(v):
            real += 1
        s = v[:]
        random.shuffle(s)
        if halts(s):
            shuffled += 1
        else:
            survivors.append(k)
        if halts(v[::-1]):
            reversed_ += 1
        i = random.randrange(len(v) - 1)
        q = v[:]
        q[i], q[i + 1] = q[i + 1], q[i]
        if halts(q):
            swapped += 1

    n = len(sample)
    print(f"{session}: {n} measures with >= {MIN_ACTIONS} actions\n")
    print(f"  real order rejected     {real:4}/{n}  ({100*real/n:5.1f}%)   <- must be 0.0%")
    print(f"  reversed rejected       {reversed_:4}/{n}  ({100*reversed_/n:5.1f}%)")
    print(f"  full shuffle rejected   {shuffled:4}/{n}  ({100*shuffled/n:5.1f}%)")
    print(f"  adjacent swap rejected  {swapped:4}/{n}  ({100*swapped/n:5.1f}%)   <- tighten to raise")
    if survivors:
        print(f"\n  order-insensitive under full shuffle: {len(survivors)}")
        for k in survivors[:8]:
            states = collections.Counter()
            for r in by[k]:
                for e in h.parse_row(r["ActionText"])[0]:
                    if e.state:
                        states[e.state] += 1
            print(f"    {k}: {dict(states)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "2025R1",
         int(sys.argv[2]) if len(sys.argv) > 2 else 400)
