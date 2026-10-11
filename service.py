"""
InstaTrust intelligent service — the instant-approval lane with Gen-4 layers.

    Retrieval  instant-lane policy; each routing reason cites its clause
    Context    requested amount vs largest completed loan, recency, open loans,
               dealer risk, lane guardrail state
    Memory     a per-customer ledger (loans, repayments, misses, defaults),
               every decision, every outcome, per-dealer performance
    Feedback   outcomes update the ledger; dealer and lane guardrails tighten
               automatically (safe direction); loosening needs a human

v1 answered one question: "has this customer earned trust?". v2 adds
"trust for *this* loan, at *this* dealer, *now*?" -- and every added check
can only move an applicant from the instant lane to manual review, never
the other way.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from approval_engine import (
    INSTANT_APPROVAL_MINUTES, MANUAL_REVIEW_MINUTES, MAX_MISSED_PAYMENTS_FOR_TRUST,
    Applicant, ApprovalPath, LoanHistory, decide,
)
from gen4 import Context, KnowledgeBase, LLMClient, Memory, Trace, guardrail_check
from gen4 import feedback as fb

SYSTEM = "instatrust"
HERE = Path(__file__).parent
EXPOSURE_MULTIPLE = 1.5
RECENCY_MONTHS = 36
MAX_OPEN_LOANS = 1
LANE_LIMIT = 0.03
DEALER_LIMIT = 0.08
HEADINGS = {"eligibility": "Who qualifies", "exposure": "Exposure step-up", "recency": "Recency",
            "concurrent": "Concurrent exposure", "dealer": "Dealer risk", "lane": "Lane guardrail",
            "ledger": "Customer ledger"}


def _months_between(a: str, b: date) -> int:
    d = date.fromisoformat(a)
    return (b.year - d.year) * 12 + (b.month - d.month)


class InstaTrustService:
    def __init__(self, memory: Memory | None = None, kb: KnowledgeBase | None = None,
                 llm: LLMClient | None = None):
        self.memory = memory or Memory(os.environ.get("GEN4_DB", HERE / "data" / f"{SYSTEM}.db"))
        self.kb = kb or KnowledgeBase.from_dir(HERE / "knowledge")
        self.llm = llm or LLMClient()

    # -- ledger (memory) ----------------------------------------------------------------
    def ledger(self, cid: str) -> dict:
        return self.memory.fact(f"customer:{cid}", "ledger", {"loans": []})

    def add_loan(self, cid: str, loan_id: str, amount: float, status: str = "open",
                 missed_payments: int = 0, closed_on: str | None = None) -> dict:
        if status not in ("open", "completed", "defaulted"):
            raise ValueError("status must be open, completed or defaulted")
        led = self.ledger(cid)
        led["loans"] = [l for l in led["loans"] if l["loan_id"] != loan_id] + [{
            "loan_id": loan_id, "amount": amount, "status": status, "missed_payments": missed_payments,
            "closed_on": closed_on}]
        self.memory.add_fact(f"customer:{cid}", "ledger", led, source="servicing")
        return led

    def _summary(self, led: dict, today: date) -> dict:
        loans = led["loans"]
        done = [l for l in loans if l["status"] == "completed"]
        closed = [l["closed_on"] for l in done if l.get("closed_on")]
        return {"history": LoanHistory(completed_loans=len(done),
                                       missed_payments=sum(l["missed_payments"] for l in loans),
                                       defaults=sum(1 for l in loans if l["status"] == "defaulted")),
                "max_completed_amount": max((l["amount"] for l in done), default=0.0),
                "open_loans": sum(1 for l in loans if l["status"] == "open"),
                "months_since_last_close": min((_months_between(c, today) for c in closed), default=None)}

    # -- guardrails --------------------------------------------------------------------------
    def max_missed(self) -> int:
        return int(self.memory.get_param("max_missed_payments", MAX_MISSED_PAYMENTS_FOR_TRUST))

    def dealer_status(self, dealer_id: str) -> dict:
        """Incremental-loading fix: this used to re-scan every decision+outcome for this
        dealer on every call -- called from inside decide() for every
        instant-lane applicant, so it was the hottest instance of this
        mistake in the repo. It now reads a running total that learn()
        maintains incrementally; record_outcome() always calls learn()
        before the next decide() can run, so this is never stale."""
        totals = self.memory.get_param(f"accum:{self.LEARN_KEY}:dealer:{dealer_id}", {"rows": 0, "bad": 0})
        return fb.Guardrail(f"dealer:{dealer_id}", DEALER_LIMIT, min_n=10).check(
            totals.get("bad", 0), totals.get("rows", 0))

    # -- decision ------------------------------------------------------------------------------
    def decide(self, applicant_id: str, requested_amount: float, dealer_id: str = "unknown",
               today: date | None = None) -> dict:
        today = today or date.today()
        trace = Trace()
        led = self.ledger(applicant_id)
        s = self._summary(led, today)
        returning = bool(led["loans"])
        base = decide(Applicant(applicant_id, returning, s["history"]))
        path, reasons, cited = base.path, [base.reason], ["eligibility"]
        if s["history"].defaults:
            cited.append("ledger")

        blocks = []
        if path == ApprovalPath.INSTANT:
            if s["history"].missed_payments > self.max_missed():
                blocks.append(("lane", f"lane tightened: {s['history'].missed_payments} missed payment(s) "
                                       f"exceeds the current limit of {self.max_missed()}"))
            if requested_amount > EXPOSURE_MULTIPLE * s["max_completed_amount"]:
                blocks.append(("exposure", f"requested {requested_amount:,.0f} is more than "
                                           f"{EXPOSURE_MULTIPLE}x the largest completed loan "
                                           f"({s['max_completed_amount']:,.0f})"))
            m = s["months_since_last_close"]
            if m is not None and m > RECENCY_MONTHS:
                blocks.append(("recency", f"last loan closed {m} months ago (> {RECENCY_MONTHS})"))
            if s["open_loans"] > MAX_OPEN_LOANS:
                blocks.append(("concurrent", f"{s['open_loans']} loans already open"))
            dealer = self.dealer_status(dealer_id)
            if dealer["tripped"]:
                blocks.append(("dealer", f"instant lane paused at dealer {dealer_id} "
                                         f"(default upper bound {dealer['upper_bound']:.1%})"))
        if blocks:
            path = ApprovalPath.MANUAL_REVIEW
            reasons = [f"Eligible on history, but routed to manual review: " + "; ".join(b for _, b in blocks) + "."]
            cited += [k for k, _ in blocks]

        trace.context = (Context()
                         .add("requested_amount", requested_amount)
                         .add("max_completed_amount", s["max_completed_amount"], "exposure step-up at 1.5x")
                         .add("months_since_last_close", s["months_since_last_close"], "recency limit 36")
                         .add("open_loans", s["open_loans"])
                         .add("dealer_id", dealer_id)).as_dict()
        trace.memory = {"ledger_loans": len(led["loans"]), "history": vars(s["history"])}
        trace.params = {"max_missed_payments": self.max_missed()}
        passages = []
        for k in dict.fromkeys(cited):
            passages += self.kb.search(HEADINGS[k], k=1)
        trace.cite({(p.source, p.heading): p for p in passages}.values())
        msg = self._message(path, reasons, passages)
        trace.model = {"provider": self.llm.last_provider}

        out = {"applicant_id": applicant_id, "path": path.value,
               "processing_minutes": INSTANT_APPROVAL_MINUTES if path == ApprovalPath.INSTANT else MANUAL_REVIEW_MINUTES,
               "reason": " ".join(reasons), "v1_path": base.path.value, "blocked_by": [k for k, _ in blocks],
               "counter_message": msg}
        did = self.memory.record_decision(SYSTEM, applicant_id, {"dealer_id": dealer_id,
                                          "requested_amount": requested_amount}, out)
        return {"decision_id": did, **out, "trace": trace.as_dict()}

    def _message(self, path: ApprovalPath, reasons: list[str], passages) -> str:
        def offline():
            if path == ApprovalPath.INSTANT:
                return "Approved instantly based on your repayment record with us. Thank you for coming back."
            return ("Your application is with our underwriting team; it usually takes about 30 minutes. "
                    "Nothing is needed from you right now.")
        draft = self.llm.complete(f"Write one friendly sentence for a dealer-counter customer. Route: {path.value}. "
                                  f"Do not reveal internal risk reasons: {reasons}", offline=offline, max_tokens=80)
        return self._guarded(draft, path, offline(), passages)

    def _guarded(self, draft: str, path: ApprovalPath, fallback: str, passages) -> str:
        """Post-model guardrail: two distinct ways this
        customer-facing line can go wrong even though it is grounded in the same
        policy the routing decision used -- (1) it claims instant approval for a
        path that was actually routed to manual review, or (2) it leaks the
        internal risk reasons the prompt explicitly told it to withhold (dealer
        exposure limits, missed-payment counts, etc. are not the customer's to see
        at the counter, whatever the drafting model decided to include)."""
        INTERNAL_TERMS = ("exposure", "dealer", "months_since_last_close", "open_loans",
                          "missed_payment", "upper_bound", "default", "manual_review", "blocked_by")

        def offline_check(response: str, _passages) -> tuple[bool, str]:
            low = response.lower()
            if path != ApprovalPath.INSTANT and "instant" in low and "not instant" not in low:
                return False, f"draft implies instant approval but the route is {path.value}"
            leaked = [t for t in INTERNAL_TERMS if t.replace("_", " ") in low or t in low]
            if leaked:
                return False, f"draft leaks internal risk terminology {leaked}"
            return True, ""
        is_safe, reason = guardrail_check(draft, passages, self.llm, offline=offline_check)
        if is_safe:
            return draft
        return fallback + f" (Note: guardrail replaced a draft that {reason}.)"

    # -- feedback -----------------------------------------------------------------------------------
    def record_outcome(self, decision_id: str, result: str, loan_id: str | None = None,
                       amount: float | None = None, on: date | None = None) -> dict:
        if result not in ("repaid", "missed_payment", "defaulted"):
            raise ValueError("result must be repaid, missed_payment or defaulted")
        d = self.memory.get_decision(decision_id)
        if not d:
            raise KeyError(decision_id)
        self.memory.record_outcome(decision_id, {"result": result})
        cid = d["subject"]
        lid = loan_id or f"loan-{decision_id}"
        amt = amount if amount is not None else d["features"]["requested_amount"]
        existing = next((l for l in self.ledger(cid)["loans"] if l["loan_id"] == lid), None)
        missed = (existing["missed_payments"] if existing else 0) + (result == "missed_payment")
        status = {"repaid": "completed", "missed_payment": "open", "defaulted": "defaulted"}[result]
        self.add_loan(cid, lid, amt, status, missed, (on or date.today()).isoformat() if status == "completed" else None)
        return self.learn()

    LEARN_KEY = "instatrust_learn"
    LEARN_GRACE_DAYS = 7

    def learn(self) -> dict:
        """Incremental-loading fix: used to re-pull and re-aggregate every instant-lane
        decision+outcome the system had ever logged, on every call (the classic full-rescan mistake). Now pulls only outcomes that arrived since the
        last watermark (with a grace window for late-arriving outcomes),
        and merges their deltas into running totals -- both the lane-wide
        total and a per-dealer total that dealer_status() now reads from
        instead of re-scanning."""
        new = fb.new_rows_since(self.memory, SYSTEM, self.LEARN_KEY, grace_days=self.LEARN_GRACE_DAYS)
        new_instant = [d for d in new if d["output"]["path"] == "instant"]
        new_bad = sum(1 for d in new_instant if d["outcome"]["result"] == "defaulted")
        totals = fb.accumulate(self.memory, self.LEARN_KEY, rows=len(new_instant), bad=new_bad)
        lane = fb.Guardrail("instant_lane_default_rate", LANE_LIMIT, min_n=30).check(
            totals.get("bad", 0), totals.get("rows", 0))
        action = None
        if lane["tripped"] and self.max_missed() > 0:
            self.memory.set_param("max_missed_payments", 0, "lane guardrail tripped: auto-tighten (safe direction)")
            action = "instant lane tightened: missed payments allowed 1 -> 0"
        self.memory.add_fact("lane:instant", "guardrail", lane)

        dealer_deltas: dict[str, dict] = {}
        for d in new_instant:
            dealer_id = d["features"].get("dealer_id")
            if not dealer_id:
                continue
            bucket = dealer_deltas.setdefault(dealer_id, {"rows": 0, "bad": 0})
            bucket["rows"] += 1
            bucket["bad"] += int(d["outcome"]["result"] == "defaulted")
        for dealer_id, delta in dealer_deltas.items():
            fb.accumulate(self.memory, f"{self.LEARN_KEY}:dealer:{dealer_id}", rows=delta["rows"], bad=delta["bad"])
        fb.mark_processed(self.memory, self.LEARN_KEY, new)

        # The returned snapshot must cover every dealer ever seen in the
        # instant lane, not just the ones in this batch -- callers (e.g.
        # seed.py) call learn() once at the end expecting a full picture.
        # Track the dealer set itself incrementally too, rather than
        # re-deriving it by re-scanning every decision.
        known_key = f"{self.LEARN_KEY}:known_dealers"
        known = set(self.memory.get_param(known_key, []))
        if dealer_deltas and not dealer_deltas.keys() <= known:
            known |= set(dealer_deltas)
            self.memory.set_param(known_key, sorted(known), reason="incremental learn(): track dealer set")
        return {"lane": lane, "action": action,
                "dealers": {k: self.dealer_status(k)["status"] for k in sorted(known)}}
