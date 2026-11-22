"""Replay a public, deterministic cutting audit with a separate exact-cover oracle."""
import argparse
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import json
import random
import sys

sys.dont_write_bytecode=True
from robust_solve import solve
from certify import verify
from run import solve as old_solve

HERE=Path(__file__).resolve().parent


def freeze():
    def order(lot,stock,trim_left,trim_right,kerf_min,kerf_max,parts):
        return dict(lot=lot,stock=stock,trim_left=trim_left,trim_right=trim_right,
                    kerf_min=kerf_min,kerf_max=kerf_max,parts=parts)
    rows=[
        order("内点刀缝陷阱",100,0,0,2,4,[49,47]),
        order("端储备迫使分卷",100,4,4,0,0,[48,48]),
        order("短余尾无法分离",100,4,3,1,3,[92]),
        order("恰好抵端无尾切",100,4,3,1,3,[93]),
        order("长件优先多开一卷",1014,6,8,0,0,[600,500,300,200,200,200]),
        order("三卷长度虚满",1014,6,8,2,2,[488,488,488,358,338,328,288,214])]
    rng=random.Random(27508)
    for i in range(60):
        stock=rng.choice([80,120,160,200])
        left=rng.randrange(0,9)
        right=rng.randrange(0,9)
        lo=rng.randrange(0,4)
        hi=lo+rng.randrange(0,6)
        parts=[rng.randint(int(stock*.12),int(stock*.77)) for j in range(4+i%7)]
        rows.append(order("随机%02d"%(i+1),stock,left,right,lo,hi,parts))
    return rows


def oracle(o):
    lengths=o["parts"]
    n=len(lengths)
    feasible=[[] for _ in lengths]
    for mask in range(1,1<<n):
        picked=[x for j,x in enumerate(lengths) if mask>>j & 1]
        for k in range(o["kerf_min"],o["kerf_max"]+1):
            pos=o["trim_left"]
            for j,x in enumerate(picked):
                pos+=x+(k if j else 0)
            available_end=o["stock"]-o["trim_right"]
            if pos!=available_end and pos+k>available_end:
                break
        else:
            lowbit=(mask&-mask).bit_length()-1
            feasible[lowbit].append(mask)
    @lru_cache(None)
    def partitions(mask):
        if not mask:return 0
        first=(mask&-mask).bit_length()-1
        valid=[group for group in feasible[first] if mask&group==group]
        return min([1+partitions(mask^g) for g in valid],default=n+1)
    ans=partitions((1<<n)-1)
    return ans if ans<=n else None


def unsafe_legacy(o):
    # Give the legacy method the two trim reserves and the largest blade width.
    # Its original accounting ignores the potential last cut to release the offcut.
    net=o["stock"]-o["trim_left"]-o["trim_right"]
    if max(o["parts"])>net:return True
    r=old_solve({"lot":o["lot"],"stock":net,"kerf":o["kerf_max"],"parts":o["parts"]})
    for roll in r["optimum"]:
        for k in range(o["kerf_min"],o["kerf_max"]+1):
            tail=net-(sum(roll)+(len(roll)-1)*k)
            if tail!=0 and tail<k:return True
    return False


def tamper(order,certificate):
    failures={}
    for mode in ["repeat_id","change_length","omit_scenario","alter_offcut","understate_rolls"]:
        c=deepcopy(certificate)
        if mode=="repeat_id":
            # Exchange equal-length identities so arithmetic still balances.
            ids=[i for i,x in enumerate(order["parts"]) if x==200]
            for roll in c["rolls"]:
                if ids[0] in roll["item_ids"]:
                    roll["item_ids"][roll["item_ids"].index(ids[0])]=ids[1]
        elif mode=="change_length":c["rolls"][0]["parts_mm"][0]+=1
        elif mode=="omit_scenario":c["rolls"][0]["states"].pop()
        elif mode=="alter_offcut":c["rolls"][0]["states"][0]["offcut_mm"]+=1
        else:c["nrolls"]-=1
        try:verify(order,c)
        except ValueError as e:failures[mode]=str(e)
        else:raise AssertionError(mode+" not caught")
    return failures


def replay(orders):
    audits=[];certs=[]
    for o in orders:
        prod=solve(o)
        n=prod.get("nrolls")
        independent=oracle(o)
        assert n==independent,o
        if n is not None:verify(o,prod)
        endpoint=solve(o,endpoints_only=True).get("nrolls")
        audits.append(dict(lot=o["lot"],optimum=n,independent=independent,
                           ffd=prod.get("ffd_rolls"),endpoints_only_n=endpoint,
                           ignoring_tail_unsafe=unsafe_legacy(o)))
        certs.append(prod)
    assert [a["optimum"] for a in audits[:6]]==[2,2,None,1,2,4]
    random_rows=audits[6:]
    def summary(rows):
        return dict(n=len(rows),exact_matches=sum(a["optimum"]==a["independent"] for a in rows),
                    infeasible=sum(a["optimum"] is None for a in rows),
                    ffd_worse=sum(a["optimum"] is not None and a["ffd"]>a["optimum"] for a in rows),
                    endpoints_understate=sum(a["endpoints_only_n"] is not None and
                        (a["optimum"] is None or a["endpoints_only_n"]<a["optimum"]) for a in rows),
                    tail_ignored_unsafe=sum(a["ignoring_tail_unsafe"] for a in rows))
    return certs,dict(summary=dict(all=summary(audits),random=summary(random_rows)),
                      tamper_checks=tamper(orders[4],certs[4]),audits=audits)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze",action="store_true")
    parser.add_argument("--audit",type=Path,default=HERE/"稳健复核.json")
    parser.add_argument("--certs",type=Path,default=HERE/"逐卷证书.json")
    args=parser.parse_args()
    source=HERE/"data"/"robust_orders.json"
    def write(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    if args.freeze:write(source,freeze())
    certs,result=replay(json.loads(source.read_text(encoding="utf8")))
    write(args.audit,result);write(args.certs,certs)
    print(json.dumps(result["summary"],ensure_ascii=False))
