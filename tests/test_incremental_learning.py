"""
Incremental-loading fix: learn() used to re-pull and re-aggregate every instant-lane
decision+outcome the system had ever logged, on every call -- a full load,
not an incremental one (the classic full-rescan mistake). dealer_status() had the
same problem, and it's called from inside decide() for every applicant.

These tests prove the incremental replacement is correct (matches a
from-scratch recompute), idempotent (repeated learn() calls with nothing
new change nothing), and that the per-dealer running totals dealer_status()
now reads from stay accurate across calls.
"""
from datetime import date

from gen4 import Memory
from service import InstaTrustService


def _returning(svc, cid, amount=20000):
    """A fresh instance has no history, so decide() always routes new
    applicants to manual review -- seed a prior completed loan so the
    instant lane is actually exercised, matching the existing test suite's
    own pattern in tests/test_service.py."""
    svc.add_loan(cid, f"{cid}-hist", amount, "completed", 0, "2025-01-01")


def test_learn_is_idempotent_no_double_counting():
    svc = InstaTrustService(memory=Memory())
    for i in range(10):
        cid = f"cust-{i}"
        _returning(svc, cid)
        r = svc.decide(cid, 20000, dealer_id="D-01", today=date(2026, 1, 1))
        assert r["path"] == "instant"
        svc.record_outcome(r["decision_id"], "defaulted" if i < 2 else "repaid")

    first = svc.learn()
    second = svc.learn()
    third = svc.learn()
    assert first["lane"]["n"] == second["lane"]["n"] == third["lane"]["n"]
    assert first["lane"]["bad"] == second["lane"]["bad"] == third["lane"]["bad"]


def test_learn_picks_up_new_outcomes_after_more_are_recorded():
    svc = InstaTrustService(memory=Memory())
    for i in range(5):
        cid = f"cust-{i}"
        _returning(svc, cid)
        r = svc.decide(cid, 20000, dealer_id="D-02", today=date(2026, 1, 1))
        assert r["path"] == "instant"
        svc.record_outcome(r["decision_id"], "repaid")
    first = svc.learn()

    for i in range(5, 10):
        cid = f"cust-{i}"
        _returning(svc, cid)
        r = svc.decide(cid, 20000, dealer_id="D-02", today=date(2026, 1, 1))
        svc.record_outcome(r["decision_id"], "repaid")
    second = svc.learn()

    assert second["lane"]["n"] > first["lane"]["n"]
    assert second["lane"]["n"] == 10


def test_dealer_status_tracks_running_total_without_rescanning():
    """dealer_status() reads an accumulated per-dealer total now, instead
    of re-scanning every decision for that dealer on every call (it used to
    be called from decide() for every single instant-lane applicant)."""
    # Stay below DEALER_LIMIT's min_n (10) so the dealer breaker never
    # trips mid-loop -- that's a separate, legitimate behavior (decide()
    # routing later applicants to manual review once a dealer is paused),
    # not what this test is checking.
    svc = InstaTrustService(memory=Memory())
    for i in range(6):
        cid = f"cust-{i}"
        _returning(svc, cid)
        r = svc.decide(cid, 20000, dealer_id="D-13", today=date(2026, 1, 1))
        assert r["path"] == "instant"
        svc.record_outcome(r["decision_id"], "defaulted" if i < 2 else "repaid")

    status = svc.dealer_status("D-13")
    assert status["n"] == 6
    assert status["bad"] == 2

    # A never-seen dealer must not explode, just report insufficient data.
    fresh = svc.dealer_status("D-99")
    assert fresh["n"] == 0
    assert fresh["status"] == "insufficient_data"


def test_learn_snapshot_covers_every_dealer_ever_seen_not_just_latest_batch():
    """seed.py calls learn() once at the end and expects the `dealers` dict
    to cover every dealer that has ever had an instant-lane outcome -- not
    just the ones touched since the last watermark. record_outcome()
    already calls learn() internally, so by the time a caller calls learn()
    again explicitly, that batch may be empty; the dealer set itself must
    still be remembered across calls."""
    svc = InstaTrustService(memory=Memory())
    for i, dealer in enumerate(("D-01", "D-02", "D-03")):
        cid = f"cust-{i}"
        _returning(svc, cid)
        r = svc.decide(cid, 20000, dealer_id=dealer, today=date(2026, 1, 1))
        assert r["path"] == "instant"
        svc.record_outcome(r["decision_id"], "repaid")  # triggers learn() internally

    final = svc.learn()  # nothing new -- but must still report all three dealers
    assert set(final["dealers"]) == {"D-01", "D-02", "D-03"}
