#!/usr/bin/env python3
"""
Seed InstaTrust with a synthetic customer ledger and 12 months of dealer-
counter applications.

    python seed.py [--reset] [--if-empty]

900 customers, 70% with prior loans (phones, consumer durables,
two-wheelers) already on the ledger, apply across 20 dealers over a year.
Applications are replayed in date order through the real service. Manual-
review cases are approved by a simulated underwriter 80% of the time.
Outcomes (repaid / missed payment / defaulted) arrive 90 days after
disbursal and flow back into the ledger, the dealer breaker and the lane
guardrail. Dealer D-13 runs a synthetic fraud ring (a quarter of its
instant-lane loans default), so its breaker has something to catch.
All data is synthetic: no real customers or dealers.
"""

from datetime import date, timedelta
from pathlib import Path

from gen4 import Memory
from gen4.seedkit import NOW, already_seeded, args, iso, mark
from service import InstaTrustService

N_CUSTOMERS, N_APPS, DAYS, LAG = 900, 1200, 365, 90
DEALERS = [f"D-{k:02d}" for k in range(1, 21)]
PRODUCTS = [("phone", 12000, 45000), ("consumer durable", 15000, 80000), ("two-wheeler", 60000, 160000)]


def main():
    a, rng = args("data/instatrust.db", "Seed InstaTrust with a synthetic ledger and application history")
    Path(a.db).parent.mkdir(parents=True, exist_ok=True)
    mem = Memory(a.db)
    if a.if_empty and already_seeded(mem):
        print(f"{a.db} already has data -- skipping seed")
        return
    svc = InstaTrustService(memory=mem)
    today = NOW.date()
    customers = [f"CU-{k:05d}" for k in range(1, N_CUSTOMERS + 1)]
    risk = {}
    for cid in customers:
        risk[cid] = rng.betavariate(1.2, 30)            # latent default propensity (mean ~4%)
        if rng.random() < 0.7:
            for j in range(rng.choice([1, 1, 2, 3])):
                _, lo, hi = rng.choice(PRODUCTS)
                closed = today - timedelta(days=DAYS + rng.randint(30, 1500))
                missed = 1 if rng.random() < 0.18 else (2 if rng.random() < 0.05 else 0)
                status = "defaulted" if rng.random() < risk[cid] * 0.6 else "completed"
                svc.add_loan(cid, f"HIST-{j}", round(rng.uniform(lo, hi), -2), status, missed,
                             closed.isoformat() if status == "completed" else None)

    apps = sorted((rng.uniform(0, DAYS), rng.choice(customers)) for _ in range(N_APPS))
    apps.reverse()   # oldest first
    s = {"applications": 0, "instant": 0, "manual": 0, "disbursed": 0, "repaid": 0, "missed_payment": 0,
         "defaulted": 0}
    for n, (days_ago, cid) in enumerate(apps):
        on = today - timedelta(days=int(days_ago))
        dealer = rng.choice(DEALERS)
        _, lo, hi = rng.choice(PRODUCTS)
        ask = round(rng.uniform(lo, hi), -2)
        r = svc.decide(cid, ask, dealer, today=on)
        s["applications"] += 1
        s["instant" if r["path"] == "instant" else "manual"] += 1
        disbursed = r["path"] == "instant" or rng.random() < 0.8
        outcome_ts = None
        if disbursed and days_ago > LAG:
            s["disbursed"] += 1
            p_def = risk[cid] * (2.5 if r["blocked_by"] == ["exposure"] else 1.0)
            if dealer == "D-13" and r["path"] == "instant":
                p_def = max(p_def, 0.25)
            x = rng.random()
            result = "defaulted" if x < p_def else ("missed_payment" if x < p_def + 0.08 else "repaid")
            svc.record_outcome(r["decision_id"], result, loan_id=f"L-{n:05d}", amount=ask,
                               on=on + timedelta(days=LAG))
            s[result] += 1
            outcome_ts = iso(days_ago - LAG)
        mem.backdate(r["decision_id"], iso(days_ago), outcome_ts)

    g = svc.learn()
    mark(mem, "instatrust", a.seed, s)
    print(f"seeded {a.db}: {s}")
    print(f"lane: {g['lane']['status']} (observed {g['lane']['observed_rate']}), action: {g['action']}")
    print("dealers not ok:", {k: v for k, v in g["dealers"].items() if v != "ok"})


if __name__ == "__main__":
    main()
