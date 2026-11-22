"""Check physical certificates independently. Positive certificates prove feasibility only."""
import argparse
from collections import Counter
import json
from pathlib import Path


def verify(order, cert):
    if cert["lot"]!=order["lot"] or cert["status"]!="ok":
        raise ValueError("expected a positive certificate linked to this lot")
    pieces=order["parts"]
    usable=order["stock"]-order["trim_left"]-order["trim_right"]
    if cert["usable_mm"]!=usable or cert["nrolls"]!=len(cert["rolls"]):
        raise ValueError("roll dimensions/count incorrect")
    counts=Counter()
    for roll in cert["rolls"]:
        ids=roll["item_ids"]
        if not ids or any(type(i) is not int or not 0<=i<len(pieces) for i in ids):
            raise ValueError("bad or missing piece ID")
        counts.update(ids)
        lengths=[pieces[i] for i in ids]
        if roll["parts_mm"]!=lengths:raise ValueError("piece length changed")
        states=roll["states"]
        required=list(range(order["kerf_min"],order["kerf_max"]+1))
        if [s["kerf"] for s in states]!=required:raise ValueError("missing width scenario")
        for state in states:
            k=state["kerf"]
            cursor=order["trim_left"]
            for j,x in enumerate(lengths):
                if j:cursor+=k
                cursor+=x
            right=order["stock"]-order["trim_right"]
            exact=cursor==right
            terminal=0 if exact else k
            offcut=right-cursor-terminal
            ok=(offcut>=0 and state["feasible"] is True and state["exact_end"]==exact
                and state["tail_cut_mm"]==terminal and state["gaps_mm"]==(len(ids)-1)*k
                and state["offcut_mm"]==offcut)
            if not ok:raise ValueError("physical cut/trim/kerf ledger failed")
    if counts!=Counter(range(len(pieces))):raise ValueError("missing or duplicated item")
    return True


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("orders",type=Path)
    p.add_argument("certificates",type=Path)
    args=p.parse_args()
    orders=json.loads(args.orders.read_text(encoding="utf8"))
    certs=json.loads(args.certificates.read_text(encoding="utf8"))
    if len(orders)!=len(certs):p.error("order count differs")
    checked=0
    try:
        for order,cert in zip(orders,certs):
            if cert["status"]=="infeasible":
                # A single item that cannot be separated at an allowed width proves infeasibility.
                usable=order["stock"]-order["trim_left"]-order["trim_right"]
                i,k=cert["item_id"],cert["kerf_witness"]
                if type(i) is not int or not 0<=i<len(order["parts"]):
                    raise ValueError("invalid infeasibility witness")
                free=usable-order["parts"][i]
                if not (cert["lot"]==order["lot"] and cert["part_mm"]==order["parts"][i]
                        and order["kerf_min"]<=k<=order["kerf_max"] and cert["available_after_piece_mm"]==free
                        and free!=0 and free<k):
                    raise ValueError("infeasibility witness does not prove the obstruction")
            else:
                verify(order,cert)
            checked+=1
    except (ValueError,AssertionError,TypeError,KeyError) as e:p.exit(2,f"invalid certificate: {e}\n")
    print(f"{checked} feasibility certificates verified")
