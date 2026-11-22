"""Exact one-dimensional cutting with kerf between adjacent retained pieces.
Outputs optional end offcuts as unused length; the contract charges no end trim.
"""
from collections import Counter
from itertools import chain
from math import ceil
import json
from pathlib import Path


def used(pieces, kerf):
    return sum(pieces) + max(len(pieces)-1, 0)*kerf


def greedy(parts, capacity, kerf):
    rolls = []
    for p in sorted(parts, reverse=True):
        for roll in rolls:
            if used(roll+[p], kerf) <= capacity:
                roll.append(p)
                break
        else:
            rolls.append([p])
    return rolls


def solve(order):
    parts, cap, gap = order['parts'], order['stock'], order['kerf']
    if not parts or len(parts)>22 or cap<=0 or gap<0 or min(parts)<=0 or max(parts)>cap:
        raise ValueError("Quantity/length outside supported range")
    if any(type(v) is not int for v in [cap,gap,*parts]):
        raise ValueError("Use integer millimetres")
    start = greedy(parts, cap, gap)
    lower = ceil(sum(p+gap for p in parts)/(cap+gap))
    ordered = sorted(parts, reverse=True)
    attempts = []
    for count in range(lower,len(start)+1):
        rolls = [[] for _ in range(count)]
        free = [cap+gap]*count
        seen = set()
        def place(index):
            if index == len(ordered):
                return True
            key = index, tuple(sorted(free))
            if key in seen:
                return False
            seen.add(key)
            tried = set()
            for i, room in enumerate(free):
                amount = ordered[index]+gap
                if room < amount or room in tried:
                    continue
                tried.add(room)
                free[i] -= amount
                rolls[i].append(ordered[index])
                if place(index+1):
                    return True
                rolls[i].pop()
                free[i] += amount
            return False
        found = place(0)
        attempts.append(dict(rolls=count, feasible=found, distinct_states=len(seen)))
        if found:
            break
    assert Counter(chain.from_iterable(rolls)) == Counter(parts)
    assert all(used(r,gap)<=cap for r in rolls) and all(rolls)
    return dict(lot=order['lot'], capacity=cap, kerf=gap, first_fit_decreasing=start,
                lower_bound=lower, search=attempts, optimum=rolls,
                offcut_lengths=[cap-used(r,gap) for r in rolls])


if __name__ == '__main__':
    source = Path(__file__).resolve().parent / 'data/orders.json'
    with source.open(encoding='utf-8') as f:
        orders = json.load(f)
    results = [solve(o) for o in orders]
    for o,r in zip(orders,results):
        assert len(solve({**o, 'parts':o['parts'][::-1]})['optimum'])==len(r['optimum'])
    try:
        solve({'parts':[1001],'stock':1000,'kerf':0})
    except ValueError as e:
        rejection = str(e)
    else:
        raise AssertionError("oversize part not detected")
    print(json.dumps({'runs':results,'oversize_test':rejection},ensure_ascii=False,indent=2))
