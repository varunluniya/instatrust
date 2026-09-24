import os
import tempfile

os.environ["GEN4_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["GEN4_LLM_PROVIDER"] = "offline"

from datetime import date, timedelta  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

c = TestClient(app)


def test_ledger_decide_feedback():
    c.post("/customers/C1/loans", json={"loan_id": "L1", "amount": 25000, "closed_on": (date.today() - timedelta(days=60)).isoformat()})
    r = c.post("/decide", json={"applicant_id": "C1", "requested_amount": 30000, "dealer_id": "D-01"}).json()
    assert r["path"] == "instant"
    f = c.post("/feedback", json={"decision_id": r["decision_id"], "result": "repaid"}).json()
    assert f["lane"]["status"] == "insufficient_data"
    assert len(c.get("/customers/C1").json()["loans"]) == 2
    assert c.post("/feedback", json={"decision_id": "x", "result": "repaid"}).status_code == 404
    assert c.post("/decide", json={"applicant_id": "C1", "requested_amount": -5}).status_code == 422
