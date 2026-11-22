"""Exact roll grouping with two end reserves and an integer range of kerfs.

One blade width applies to a roll in each scenario. Different rolls may encounter
different allowed widths. A remaining offcut must be separated by one final cut.
"""
import argparse
import json
from pathlib import Path


def parse(order):
    for name in ("stock", "trim_left", "trim_right", "kerf_min", "kerf_max"):
        if type(order[name]) is not int or order[name]<0:
            raise ValueError(f"{name} must be a nonnegative integer in mm")
    lo, hi = order["kerf_min"], order["kerf_max"]
    if hi < lo or hi-lo>32:
        raise ValueError("kerf range must contain 1..33 integer widths")
    if order["stock"] <= order["trim_left"] + order["trim_right"]:
        raise ValueError("end reserves consume the roll")
    parts=order["parts"]
    if not 1<=len(parts)<=16 or any(type(x) is not int or x<=0 for x in parts):
        raise ValueError("support 1..16 positive integer piece lengths")
    return order["stock"]-order["trim_left"]-order["trim_right"], range(lo,hi+1)


def physical_states(usable, length, n, widths):
    states=[]
    for k in widths:
        gap_total=(n-1)*k
        residual=usable-length-gap_total
        tail=0 if residual==0 else k
        scrap=residual-tail
        states.append({"kerf":k,"gaps_mm":gap_total,"tail_cut_mm":tail,"offcut_mm":scrap,
                       "exact_end":residual==0,"feasible":scrap>=0})
    return states


def solve(order, endpoints_only=False):
    usable,widths=parse(order)
    if endpoints_only:
        widths=sorted({widths[0],widths[-1]})
    parts=order["parts"]
    ordered=sorted(range(len(parts)),key=lambda j:-parts[j])
    cache={}
    def fits(length,n):
        key=length,n
        if key not in cache:
            cache[key]=all(x["feasible"] for x in physical_states(usable,length,n,widths))
        return cache[key]
    for i in ordered:
        if not fits(parts[i],1):
            failure=next(row for row in physical_states(usable,parts[i],1,widths) if not row["feasible"])
            return {"lot":order["lot"],"status":"infeasible","reason":"item cannot be separated",
                    "item_id":i,"part_mm":parts[i],"kerf_witness":failure["kerf"],
                    "available_after_piece_mm":usable-parts[i]}
    greedy=[]
    for i in ordered:
        for group in greedy:
            if fits(sum(parts[j] for j in group)+parts[i],len(group)+1):
                group.append(i)
                break
        else:greedy.append([i])
    high=max(widths)
    numerator=sum(parts)+len(parts)*high
    lower=(numerator+usable+high-1)//(usable+high)
    attempts=[]
    for count in range(lower,len(greedy)+1):
        bins=[[] for _ in range(count)]
        sums=[0]*count
        seen=set()
        def assign(index):
            if index==len(ordered):return True
            code=index,tuple(sorted((n,len(g)) for n,g in zip(sums,bins)))
            if code in seen:return False
            seen.add(code)
            i=ordered[index]
            tried=set()
            for j,group in enumerate(bins):
                state=sums[j],len(group)
                if state in tried:continue
                tried.add(state)
                if not fits(sums[j]+parts[i],len(group)+1):continue
                group.append(i)
                sums[j]+=parts[i]
                if assign(index+1):return True
                sums[j]-=parts[i]
                group.pop()
            return False
        found=assign(0)
        attempts.append({"rolls":count,"feasible":found,"states":len(seen)})
        if found:break
    rolls=[]
    for group in bins:
        total=sum(parts[j] for j in group)
        rolls.append({"item_ids":group[:],"parts_mm":[parts[j] for j in group],
                      "states":physical_states(usable,total,len(group),widths)})
    return {"lot":order["lot"],"status":"ok","usable_mm":usable,"nrolls":len(rolls),
            "lower_bound":lower,"ffd_rolls":len(greedy),"attempts":attempts,"rolls":rolls}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("orders",type=Path,help="UTF-8 JSON, list of orders")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    try:
        orders=json.loads(args.orders.read_text(encoding="utf-8-sig"))
        report=[solve(order) for order in orders]
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    except (ValueError,KeyError,TypeError,OSError) as exc:
        parser.exit(2,f"invalid input or output: {exc}\n")
    print(f"Checked {len(report)} orders")
