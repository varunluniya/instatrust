#!/usr/bin/env python3
"""
InstaTrust eval gate. Segments:
  v1_batch     the 7 original sample applicants route exactly as in v1
  context      exposure step-up, recency, concurrent loans each block instant
  one_way      no v2 check ever moves a v1-manual applicant into instant
  dealer       a dealer with confident excess defaults is paused automatically
  lane         lane guardrail auto-tightens missed-payment allowance to 0
"""

from datetime import date

from gen4 import KnowledgeBase, LLMClient, Memory
from gen4.evals import EvalCase, gate, print_and_exit, run_eval
from service import InstaTrustService
from simulate import APPLICANTS

TODAY = date(2026, 9, 1)


def fresh():
    return InstaTrustService(Memory(), KnowledgeBase.from_dir("knowledge"), LLMClient(provider="offline"))


def load_v1(svc, a):
    h = a.history
    if not a.is_returning_customer:
        return
    for k in range(h.completed_loans):
        svc.add_loan(a.applicant_id, f"c{k}", 50000, "completed", h.missed_payments if k == 0 else 0, "2026-01-01")
    for k in range(h.defaults):
        svc.add_loan(a.applicant_id, f"d{k}", 50000, "defaulted")
    if h.completed_loans == 0 and h.defaults == 0:
        svc.add_loan(a.applicant_id, "open0", 50000, "open")


def system(inp):
    svc = fresh()
    kind = inp[0]
    if kind == "v1":
        a = inp[1]
        load_v1(svc, a)
        return svc.decide(a.applicant_id, 40000, today=TODAY)["path"]
    if kind == "ctx":
        svc.add_loan("c", "p", 20000, "completed", 0, inp[2])
        for k in range(inp[3]):
            svc.add_loan("c", f"o{k}", 10000, "open")
        return svc.decide("c", inp[1], today=TODAY)["blocked_by"]
    if kind == "one_way":
        moved = 0
        for a in APPLICANTS:
            s2 = fresh()
            load_v1(s2, a)
            r = s2.decide(a.applicant_id, 40000, today=TODAY)
            moved += r["v1_path"] == "manual_review" and r["path"] == "instant"
        return moved
    if kind == "dealer":
        for k in range(20):
            svc.add_loan(f"x{k}", "p", 50000, "completed", 0, "2026-01-01")
            r = svc.decide(f"x{k}", 40000, "D-13", today=TODAY)
            svc.record_outcome(r["decision_id"], "defaulted" if k % 2 == 0 else "repaid")
        svc.add_loan("new", "p", 50000, "completed", 0, "2026-01-01")
        return (svc.decide("new", 40000, "D-13", today=TODAY)["blocked_by"],
                svc.decide("new", 40000, "D-01", today=TODAY)["path"])
    if kind == "lane":
        for k in range(40):
            svc.add_loan(f"y{k}", "p", 50000, "completed", 0, "2026-01-01")
            r = svc.decide(f"y{k}", 40000, f"D-{k}", today=TODAY)
            svc.record_outcome(r["decision_id"], "defaulted" if k % 4 == 0 else "repaid")
        svc.add_loan("m", "p", 50000, "completed", 1, "2026-01-01")
        return (svc.max_missed(), svc.decide("m", 40000, today=TODAY)["blocked_by"])
    raise ValueError(kind)


V1 = {"A-01": "manual_review", "A-02": "instant", "A-03": "instant", "A-04": "manual_review",
      "A-05": "manual_review", "A-06": "manual_review", "A-07": "instant"}
cases = [EvalCase(a.applicant_id, ("v1", a), V1[a.applicant_id[:4]], "v1_batch") for a in APPLICANTS]
cases += [
    EvalCase("exposure-3x", ("ctx", 60000, "2026-01-01", 0), ["exposure"], "context"),
    EvalCase("exposure-1.5x-ok", ("ctx", 30000, "2026-01-01", 0), [], "context"),
    EvalCase("recency-40-months", ("ctx", 20000, "2023-05-01", 0), ["recency"], "context"),
    EvalCase("two-open-loans", ("ctx", 20000, "2026-01-01", 2), ["concurrent"], "context"),
    EvalCase("never-promotes", ("one_way",), 0, "one_way"),
    EvalCase("dealer-paused", ("dealer",), (["dealer"], "instant"), "dealer"),
    EvalCase("lane-tightens", ("lane",), (0, ["lane"]), "lane"),
]

if __name__ == "__main__":
    report = run_eval(cases, system, runs=3)
    ok, why = gate(report, min_accuracy=1.0, min_consistency=1.0)
    print_and_exit("InstaTrust", report, ok, why)
