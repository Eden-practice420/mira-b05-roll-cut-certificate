"""Audit short cutting orders with a separate exact set-partition DP.

The production solver inserts individual pieces into candidate rolls. This oracle
enumerates every feasible subset as one roll and partitions the order's bitmask.
"""
import argparse
from collections import Counter
from functools import lru_cache
import json
from pathlib import Path
import random
import sys

sys.dont_write_bytecode = True
from run import solve


def optimal_partition(order):
    lengths = order["parts"]
    n = len(lengths)
    # Count physical kerfs directly; no effective-capacity transformation here.
    subsets = [[] for _ in range(n)]
    for mask in range(1, 1 << n):
        pieces = [p for i, p in enumerate(lengths) if mask & (1 << i)]
        occupied = sum(pieces) + (len(pieces) - 1) * order["kerf"]
        if occupied <= order["stock"]:
            first = (mask & -mask).bit_length() - 1
            subsets[first].append(mask)

    @lru_cache(None)
    def visit(remain):
        if not remain:
            return (0, ())
        first = (remain & -remain).bit_length() - 1
        candidates = []
        for group in subsets[first]:
            if group & remain != group:
                continue
            count, suffix = visit(remain ^ group)
            candidates.append((count + 1, (group,) + suffix))
        return min(candidates)

    count, masks = visit((1 << n) - 1)
    witness = [[p for i,p in enumerate(lengths) if mask & (1 << i)] for mask in masks]
    return count, witness


def inspect(order):
    actual = solve(order)
    optimal, dp_plan = optimal_partition(order)
    witness = actual["optimum"]
    assert Counter(p for roll in witness for p in roll) == Counter(order["parts"])
    assert all(sum(roll)+(len(roll)-1)*order["kerf"] <= order["stock"] for roll in witness)
    assert optimal == len(witness), (order, actual, dp_plan)
    for rejected in actual["search"][:-1]:
        assert rejected["rolls"] < optimal and rejected["feasible"] is False
    return dict(input=order, bound=actual["lower_bound"], optimum=optimal,
                production_plan=witness, oracle_plan=dp_plan, search=actual["search"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("短订单压力测试.json"))
    args = parser.parse_args()
    seed=59281
    rng=random.Random(seed)
    special=dict(lot="三卷无整配", stock=1000, kerf=2, parts=[488,488,488,358,338,328,288,214])
    certificate=inspect(special)
    assert certificate["bound"]==3 and certificate["optimum"]==4
    assert certificate["search"][0]["feasible"] is False
    trials=[]
    for i in range(80):
        stock=rng.choice([100,250,500,1000])
        n=rng.randint(3,10)
        gap=rng.choice([0,1,2,3])
        parts=[rng.randint(max(1,stock//10),stock*7//10) for _ in range(n)]
        trials.append(inspect(dict(lot=f"stress-{i+1:02d}",stock=stock,kerf=gap,parts=parts)))
    baseline_orders=json.loads((Path(__file__).resolve().parent/"data"/"orders.json").read_text(encoding="utf-8"))
    report=dict(seed=seed, adversarial=certificate, original_orders=[inspect(o) for o in baseline_orders],
                random_summary={"n":len(trials),"agreed":len(trials),
                                "bound_unattainable":sum(t["optimum"]>t["bound"] for t in trials),
                                "worst_gap":max(t["optimum"]-t["bound"] for t in trials)},
                random_orders=trials)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"adversarial_search":certificate["search"],"random":report["random_summary"]}))


if __name__ == "__main__":
    main()
