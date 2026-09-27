"""
Guide 4 Assignment 2 ("RAG with Guardrails") applied to InstaTrust's own
counter-message generator: one query that passes cleanly, one that fires
the guardrail, and one genuine edge case.
"""
import pytest

from approval_engine import ApprovalPath
from gen4 import KnowledgeBase, LLMClient, Memory
from service import InstaTrustService


@pytest.fixture
def svc():
    return InstaTrustService(Memory(), KnowledgeBase.from_dir("knowledge"), LLMClient(provider="offline"))


def test_passing_query_instant_message_for_an_instant_route(svc):
    draft = "Approved instantly based on your repayment record with us. Thank you for coming back."
    out = svc._guarded(draft, ApprovalPath.INSTANT, draft, passages=[])
    assert out == draft
    assert "guardrail replaced" not in out


def test_guardrail_fires_on_false_instant_claim_for_a_manual_review_route(svc):
    """The Air Canada failure shape: a fluent line that contradicts the real
    routing decision, told directly to a customer at the counter."""
    bad_draft = "Great news, you're approved instantly!"
    fallback = "Your application is with our underwriting team; it usually takes about 30 minutes."
    out = svc._guarded(bad_draft, ApprovalPath.MANUAL_REVIEW, fallback, passages=[])
    assert out != bad_draft
    assert "guardrail replaced" in out
    assert "underwriting team" in out


def test_edge_case_draft_leaks_the_internal_reason_it_was_told_to_withhold(svc):
    """Genuine edge case: the draft never claims instant approval (so the first
    check wouldn't catch it), but it leaks the internal dealer-exposure reasoning
    the prompt explicitly said to withhold from the customer."""
    leaky_draft = "Your application is under review because of dealer exposure limits on your account."
    fallback = "Your application is with our underwriting team; it usually takes about 30 minutes."
    out = svc._guarded(leaky_draft, ApprovalPath.MANUAL_REVIEW, fallback, passages=[])
    assert out != leaky_draft
    assert "guardrail replaced" in out
