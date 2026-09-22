"""
InstaTrust — instant approval for returning customers at the point of sale.

At a dealer counter (financing a two-wheeler, a phone, a consumer
durable), the standard loan process takes roughly 30 minutes of manual
underwriting review, applied uniformly whether the applicant is a
complete stranger or someone the lender has financed twice before. That
uniform 30-minute wait isn't just a minor inconvenience: it's an open
window during which a customer's interest in the purchase can decay --
they get distracted, they second-guess themselves, or they drift to a
dealer or lender who can move faster. The actual job the applicant is
"hiring" a fast approval to do is not "process my paperwork," it's
"let me lock in this purchase before I lose my nerve or my window."

InstaTrust closes that window for exactly the segment of applicants
where it's safe to: returning customers whose own repayment history
with this lender already answers the only question manual underwriting
exists to answer -- can this person be trusted to repay? For that
segment, InstaTrust skips underwriting and approves instantly. Every
other applicant -- new to the lender, or with a shaky repayment record
-- is routed to the normal manual-review queue, unchanged.
"""

from dataclasses import dataclass, field
from enum import Enum


class ApprovalPath(Enum):
    INSTANT = "instant"
    MANUAL_REVIEW = "manual_review"


# Baseline manual-review time this design is trying to close the window
# on -- matches the average wait observed in the ordinary framing of the
# underlying problem.
MANUAL_REVIEW_MINUTES = 30.0

# InstaTrust's own instant path still takes a small, real amount of time
# (pulling the record, running the rule check, confirming with the
# applicant) -- it isn't literally zero, just no longer gated behind a
# human underwriter's queue.
INSTANT_APPROVAL_MINUTES = 2.0

# A returning customer needs at least this many completed loans with
# this lender before their history is trusted at all.
MIN_COMPLETED_LOANS_FOR_TRUST = 1

# Any default in the customer's history with this lender disqualifies
# them from instant approval, regardless of how long ago it was --
# trust, once broken, doesn't get auto-restored.
DISQUALIFYING_DEFAULTS = 1

# A returning customer with more than this many missed (but eventually
# paid) payments across their history is routed to manual review rather
# than instantly approved -- late payments are a weaker signal than a
# default, but still enough recent friction to warrant a human look.
MAX_MISSED_PAYMENTS_FOR_TRUST = 1


@dataclass
class LoanHistory:
    completed_loans: int = 0
    missed_payments: int = 0  # payments made late, but eventually paid
    defaults: int = 0  # loans never repaid


@dataclass
class Applicant:
    applicant_id: str
    is_returning_customer: bool
    history: LoanHistory = field(default_factory=LoanHistory)


@dataclass
class ApprovalDecision:
    applicant_id: str
    path: ApprovalPath
    processing_minutes: float
    reason: str


def decide(applicant: Applicant) -> ApprovalDecision:
    """The core InstaTrust rule: route to instant approval only when the
    applicant's own history with this lender already answers the trust
    question manual underwriting exists to answer. Everyone else gets
    the unchanged, existing manual-review path -- this is a fast lane
    for a specific segment, not a universal shortcut."""

    if not applicant.is_returning_customer:
        return ApprovalDecision(
            applicant.applicant_id,
            ApprovalPath.MANUAL_REVIEW,
            MANUAL_REVIEW_MINUTES,
            "New applicant: no repayment history with this lender exists yet, "
            "so there is nothing to instantly trust. Routed to manual review.",
        )

    h = applicant.history

    if h.defaults >= DISQUALIFYING_DEFAULTS:
        return ApprovalDecision(
            applicant.applicant_id,
            ApprovalPath.MANUAL_REVIEW,
            MANUAL_REVIEW_MINUTES,
            f"Returning customer, but has {h.defaults} prior default(s) with "
            "this lender. Trust is not auto-restored after a default. "
            "Routed to manual review.",
        )

    if h.completed_loans < MIN_COMPLETED_LOANS_FOR_TRUST:
        return ApprovalDecision(
            applicant.applicant_id,
            ApprovalPath.MANUAL_REVIEW,
            MANUAL_REVIEW_MINUTES,
            "Returning customer, but has not yet completed a full loan cycle "
            "with this lender -- insufficient history to trust instantly. "
            "Routed to manual review.",
        )

    if h.missed_payments > MAX_MISSED_PAYMENTS_FOR_TRUST:
        return ApprovalDecision(
            applicant.applicant_id,
            ApprovalPath.MANUAL_REVIEW,
            MANUAL_REVIEW_MINUTES,
            f"Returning customer with a clean default record, but "
            f"{h.missed_payments} missed payments exceeds the threshold of "
            f"{MAX_MISSED_PAYMENTS_FOR_TRUST}. Routed to manual review.",
        )

    return ApprovalDecision(
        applicant.applicant_id,
        ApprovalPath.INSTANT,
        INSTANT_APPROVAL_MINUTES,
        f"Returning customer with {h.completed_loans} completed loan(s), "
        f"{h.missed_payments} missed payment(s), and no defaults. Own "
        "repayment history already answers the trust question -- "
        "instantly approved, manual review skipped.",
    )
