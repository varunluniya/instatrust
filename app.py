"""
InstaTrust API.   uvicorn app:app --reload    ->  http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from gen4.api import common_router
from service import InstaTrustService

service = InstaTrustService()
app = FastAPI(title="InstaTrust", version="2.0.0",
              description="Instant approval at the dealer counter for returning customers whose own ledger "
                          "answers the trust question -- for this loan size, at this dealer, now. Guardrails "
                          "tighten automatically; loosening needs a human.")
app.include_router(common_router(service, "instatrust"))


class LoanIn(BaseModel):
    loan_id: str
    amount: float = Field(..., gt=0)
    status: Literal["open", "completed", "defaulted"] = "completed"
    missed_payments: int = Field(0, ge=0)
    closed_on: date | None = None


class DecideIn(BaseModel):
    applicant_id: str
    requested_amount: float = Field(..., gt=0)
    dealer_id: str = "unknown"


class OutcomeIn(BaseModel):
    decision_id: str
    result: Literal["repaid", "missed_payment", "defaulted"]
    loan_id: str | None = None


@app.get("/", tags=["ops"])
def root():
    return {"service": "InstaTrust", "docs": "/docs",
            "flow": "POST /customers/{id}/loans (ledger) -> POST /decide -> POST /feedback"}


@app.post("/customers/{cid}/loans", tags=["ledger"])
def add_loan(cid: str, body: LoanIn):
    return service.add_loan(cid, body.loan_id, body.amount, body.status, body.missed_payments,
                            body.closed_on.isoformat() if body.closed_on else None)


@app.get("/customers/{cid}", tags=["ledger"])
def get_ledger(cid: str):
    return service.ledger(cid)


@app.post("/decide", tags=["decision"])
def decide(body: DecideIn):
    return service.decide(body.applicant_id, body.requested_amount, body.dealer_id)


@app.post("/feedback", tags=["feedback"])
def feedback(body: OutcomeIn):
    try:
        return service.record_outcome(body.decision_id, body.result, body.loan_id)
    except KeyError:
        raise HTTPException(404, "unknown decision_id")


@app.get("/guardrails", tags=["feedback"])
def guardrails():
    return service.learn()


@app.get("/dealers/{dealer_id}", tags=["feedback"])
def dealer(dealer_id: str):
    return service.dealer_status(dealer_id)
