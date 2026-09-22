"""Unit tests for the InstaTrust approval engine. Run with: pytest"""

from approval_engine import (
    Applicant,
    LoanHistory,
    decide,
    ApprovalPath,
    MANUAL_REVIEW_MINUTES,
    INSTANT_APPROVAL_MINUTES,
)


def test_new_customer_always_goes_to_manual_review():
    a = Applicant("new", is_returning_customer=False)
    d = decide(a)
    assert d.path == ApprovalPath.MANUAL_REVIEW
    assert d.processing_minutes == MANUAL_REVIEW_MINUTES


def test_clean_returning_customer_gets_instant_approval():
    a = Applicant(
        "clean-repeat",
        is_returning_customer=True,
        history=LoanHistory(completed_loans=2, missed_payments=0, defaults=0),
    )
    d = decide(a)
    assert d.path == ApprovalPath.INSTANT
    assert d.processing_minutes == INSTANT_APPROVAL_MINUTES


def test_prior_default_disqualifies_regardless_of_other_clean_history():
    a = Applicant(
        "one-default",
        is_returning_customer=True,
        history=LoanHistory(completed_loans=5, missed_payments=0, defaults=1),
    )
    d = decide(a)
    assert d.path == ApprovalPath.MANUAL_REVIEW
    assert "default" in d.reason.lower()


def test_returning_customer_with_no_completed_loans_is_not_trusted_yet():
    # They're "returning" (have an open loan) but haven't finished one --
    # there's no completed repayment cycle to trust yet.
    a = Applicant(
        "still-open",
        is_returning_customer=True,
        history=LoanHistory(completed_loans=0, missed_payments=0, defaults=0),
    )
    d = decide(a)
    assert d.path == ApprovalPath.MANUAL_REVIEW


def test_too_many_missed_payments_routes_to_manual_review():
    a = Applicant(
        "flaky",
        is_returning_customer=True,
        history=LoanHistory(completed_loans=3, missed_payments=3, defaults=0),
    )
    d = decide(a)
    assert d.path == ApprovalPath.MANUAL_REVIEW


def test_single_missed_payment_still_within_trust_threshold():
    # One missed-but-eventually-paid payment shouldn't by itself disqualify
    # an otherwise clean returning customer -- only exceeding the threshold should.
    a = Applicant(
        "one-late",
        is_returning_customer=True,
        history=LoanHistory(completed_loans=1, missed_payments=1, defaults=0),
    )
    d = decide(a)
    assert d.path == ApprovalPath.INSTANT


def test_instant_path_is_meaningfully_faster_than_manual_review():
    assert INSTANT_APPROVAL_MINUTES < MANUAL_REVIEW_MINUTES
