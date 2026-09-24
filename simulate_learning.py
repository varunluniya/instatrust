#!/usr/bin/env python3
"""
Prove-It simulation: v1 instant lane vs v2 instant lane on the same stream
of 600 returning-customer applications (seeded, deterministic).

Hidden truths of this synthetic world:
  * a customer asking for >1.5x their largest completed loan defaults 12%
    of the time (vs 1.5% otherwise) -- a phone-loan customer buying a bike
  * dealer D-13 has a fraud ring: its instant-lane loans default 25%
v1 sees neither. v2 has the exposure step-up rule from day one, and learns
the dealer problem from outcomes and pauses that dealer by itself.
"""

import random
from datetime import date

from approval_engine import Applicant, LoanHistory, decide
from gen4 import KnowledgeBase, LLMClient, Memory
from service import InstaTrustService

TODAY = date(2026, 9, 1)


def main(n=600, seed=11):
    rng = random.Random(seed)
    svc = InstaTrustService(Memory(), KnowledgeBase.from_dir("knowledge"), LLMClient(provider="offline"))
    stats = {"v1": [0, 0, 0], "v2": [0, 0, 0]}   # instant, defaults, minutes saved
    phase_rows = []
    for i in range(n):
        cid, dealer = f"c{i}", rng.choice(["D-01", "D-02", "D-07", "D-13"])
        prior = rng.choice([15000, 25000, 40000, 60000])
        svc.add_loan(cid, "old", prior, "completed", missed_payments=rng.choice([0, 0, 0, 1]),
                     closed_on="2025-11-01")
        ask = prior * (rng.uniform(2.0, 4.0) if rng.random() < 0.25 else rng.uniform(0.5, 1.4))
        p_default = 0.12 if ask > 1.5 * prior else 0.015
        if dealer == "D-13":
            p_default = 0.25
        defaulted = rng.random() < p_default
        v1 = decide(Applicant(cid, True, LoanHistory(1, 0, 0))).path.value == "instant"
        r = svc.decide(cid, ask, dealer, today=TODAY)
        v2 = r["path"] == "instant"
        for k, inst in (("v1", v1), ("v2", v2)):
            if inst:
                stats[k][0] += 1
                stats[k][1] += defaulted
                stats[k][2] += 28
        svc.record_outcome(r["decision_id"], "defaulted" if defaulted else "repaid", loan_id="new", amount=ask)
        if (i + 1) % 200 == 0:
            phase_rows.append((i + 1, dict((k, list(v)) for k, v in stats.items()),
                               svc.dealer_status("D-13")["status"]))
    print(f"{'apps':<6}{'v1 instant':>11}{'v1 def':>8}{'v1 rate':>9}{'v2 instant':>12}{'v2 def':>8}{'v2 rate':>9}   D-13 in v2")
    for n_, s, d13 in phase_rows:
        (a1, b1, _), (a2, b2, _) = s["v1"], s["v2"]
        print(f"{n_:<6}{a1:>11}{b1:>8}{b1/a1:>9.1%}{a2:>12}{b2:>8}{b2/a2:>9.1%}   {d13}")
    (a1, b1, m1), (a2, b2, m2) = stats["v1"], stats["v2"]
    print(f"\nWait minutes saved: v1 {m1:,}  v2 {m2:,} ({m2/m1:.0%} of v1's speed benefit kept)")
    print(f"Instant-lane defaults: v1 {b1} ({b1/a1:.1%})  v2 {b2} ({b2/a2:.1%})")


if __name__ == "__main__":
    main()
