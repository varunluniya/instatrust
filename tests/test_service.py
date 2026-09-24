from datetime import date

import pytest

from gen4 import KnowledgeBase, LLMClient, Memory
from service import InstaTrustService

TODAY = date(2026, 9, 1)


@pytest.fixture
def svc():
    return InstaTrustService(Memory(), KnowledgeBase.from_dir("knowledge"), LLMClient(provider="offline"))


def test_new_customer_manual_and_policy_cited(svc):
    r = svc.decide("nobody", 30000, today=TODAY)
    assert r["path"] == "manual_review"
    assert r["trace"]["retrieval"][0]["heading"] == "Who qualifies"


def test_clean_returning_customer_instant_with_friendly_message(svc):
    svc.add_loan("c", "l1", 30000, "completed", 0, "2026-02-01")
    r = svc.decide("c", 30000, today=TODAY)
    assert r["path"] == "instant" and r["processing_minutes"] == 2.0
    assert "risk" not in r["counter_message"].lower()


def test_default_in_ledger_removes_eligibility_immediately(svc):
    svc.add_loan("c", "l1", 30000, "completed", 0, "2026-02-01")
    first = svc.decide("c", 30000, today=TODAY)
    svc.record_outcome(first["decision_id"], "defaulted", loan_id="l2")
    assert svc.decide("c", 30000, today=TODAY)["path"] == "manual_review"


def test_repayment_grows_the_exposure_ceiling(svc):
    svc.add_loan("c", "l1", 20000, "completed", 0, "2026-02-01")
    assert svc.decide("c", 45000, today=TODAY)["blocked_by"] == ["exposure"]
    svc.add_loan("c", "l2", 30000, "completed", 0, "2026-06-01")
    assert svc.decide("c", 45000, today=TODAY)["path"] == "instant"


def test_small_sample_does_not_pause_a_dealer(svc):
    for k in range(10):
        svc.add_loan(f"x{k}", "p", 50000, "completed", 0, "2026-01-01")
        r = svc.decide(f"x{k}", 40000, "D-02", today=TODAY)
        svc.record_outcome(r["decision_id"], "defaulted" if k == 0 else "repaid")
    assert svc.dealer_status("D-02")["tripped"] is False


def test_invalid_inputs(svc):
    with pytest.raises(ValueError):
        svc.add_loan("c", "l", 1, "weird")
    with pytest.raises(KeyError):
        svc.record_outcome("nope", "repaid")
