# InstaTrust

_Instant approval at the dealer counter for returning customers whose own repayment record answers the trust question, checked against the loan size, the dealer and the timing. The lane protects itself: it tightens automatically and loosens only with a human._

[![ci](https://github.com/varunluniya/instatrust/actions/workflows/ci.yml/badge.svg)](https://github.com/varunluniya/instatrust/actions/workflows/ci.yml)

## What's new in v2: an intelligent, deployable service

| Layer | In InstaTrust |
|---|---|
| **Retrieval** | Instant-lane policy. The clause behind each routing reason is cited |
| **Context** | Requested amount vs largest completed loan (1.5× step-up), recency (36 months), open loans, dealer status |
| **Memory** | A per-customer ledger: loans, amounts, repayments, misses, defaults |
| **Feedback** | Outcomes → ledger → dealer circuit breaker → lane guardrail (auto-tighten only) |

Every v2 check can only move an applicant from instant to manual, never the reverse (verified in the eval gate).

**Proof** (`python simulate_learning.py`, 600 applications, hidden exposure risk and a dealer fraud ring):

| | v1 | v2 |
|---|---|---|
| Instant-lane default rate | 9.8% | **2.6%** |
| Dealer D-13 fraud ring | never noticed | paused automatically within 200 apps |
| Applicants getting the 28-minute saving | 100% | 46% (the rest are the risky ones) |

Full framework write-up: [FRAMEWORK.md](FRAMEWORK.md).

## Run it

```bash
pip install -r requirements-dev.txt
uvicorn app:app --reload        # http://127.0.0.1:8000/docs
python -m pytest -q             # original 7 tests + service/API tests
python run_evals.py
python simulate_learning.py
```

Docker: `docker build -t instatrust . && docker run -p 8000:8000 -v instatrust-data:/data instatrust` · Render: `render.yaml`.

```bash
curl -X POST localhost:8000/customers/C1/loans -H 'content-type: application/json' -d '{"loan_id":"L1","amount":25000,"closed_on":"2026-03-01"}'
curl -X POST localhost:8000/decide -H 'content-type: application/json' -d '{"applicant_id":"C1","requested_amount":60000,"dealer_id":"D-01"}'
```

| Endpoint | Purpose |
|---|---|
| `POST /customers/{id}/loans` · `GET /customers/{id}` | Ledger |
| `POST /decide` | Instant or manual, v1 path, what blocked it, counter message, trace |
| `POST /feedback` | Repaid / missed payment / defaulted → ledger + guardrails |
| `GET /guardrails` · `GET /dealers/{id}` | Lane and dealer circuit breakers |

## Demo data

`python seed.py` fills `data/instatrust.db` with synthetic history so every endpoint returns something meaningful on first run: A ledger of 900 customers with prior loans, 1,200 dealer-counter applications across 20 dealers over 12 months, 90-day outcomes, and dealer D-13's synthetic fraud ring already paused by its breaker.

```bash
python seed.py            # create data/instatrust.db
python seed.py --reset    # rebuild it from scratch
```

The Docker image seeds `/data` on first boot (set `GEN4_SEED=0` to start empty). All of it is synthetic: no real customers, patients, tickets or model outputs. `GET /health` shows the dataset's counts.

---

## The original engine (v1)

The v1 demo still runs unchanged; the service wraps it.

Instant loan approval for returning customers at the point of sale —
built around a simple idea: a lender doesn't need to re-run the same
30-minute manual underwriting review on someone whose own repayment
history already answers the only question that review exists to
answer.

### The problem

At a dealer counter (financing a two-wheeler, a phone, any
consumer-durable purchase), loan processing takes roughly 30 minutes of
manual underwriting — applied the same way whether the applicant is a
total stranger or someone the lender has already financed twice. That
uniform wait isn't just an inconvenience. It's an open window: the
longer a customer stands there, the more likely their interest in the
purchase decays — they get distracted, they second-guess the decision,
or they simply walk to a dealer or lender who can move faster. The
underlying job a fast approval is "hired" to do isn't paperwork
processing — it's locking in the sale before that window closes.

### What InstaTrust does

InstaTrust splits the applicant funnel instead of trying to speed up
manual review uniformly for everyone:

- **Returning customers with a clean, sufficient repayment history**
  (at least one completed loan, no defaults, at most one missed
  payment) are **instantly approved**, skipping manual review entirely.
- **Everyone else** — first-time applicants, anyone with a prior
  default, anyone with more than one missed payment, or a returning
  customer whose first loan is still open — goes through the
  **unchanged 30-minute manual-review path**.

This isn't a blanket shortcut; it's a targeted fast lane for exactly
the segment where the trust question has already been answered by the
lender's own records.

### Running it

```bash
pip install pytest                                     # only needed for the test suite
python3 simulate.py                                     # 7-applicant sample batch, narrated
python3 cli.py                                           # same as simulate.py
python3 cli.py --returning --loans 2 --missed 0 --defaults 0   # evaluate one applicant
python3 cli.py --new                                     # evaluate a new applicant
python3 -m pytest -v                                     # 7 tests, all passing
```

Sample output is captured in `run_output.txt`. On the bundled 7-applicant
batch: 3 of 7 are instantly approved, closing 84 of 210 total wait
minutes (40%) — while a prior default, an over-threshold count of
missed payments, and a still-open first loan are all correctly kept on
the unchanged manual-review path.

### Files

- `approval_engine.py` — the core routing rule: `decide()` returns a
  structured `ApprovalDecision` (path, processing time, and a
  human-readable reason) for any applicant.
- `simulate.py` — a 7-applicant sample batch covering the instant-path
  case and every disqualifying case (new customer, prior default, too
  many missed payments, no completed loan yet), plus a wait-time
  summary.
- `cli.py` — evaluate the bundled batch, or a single custom applicant
  from the command line.
- `test_approval_engine.py` — 7 pytest tests covering the instant path,
  each disqualifying condition, and the boundary case of exactly one
  missed payment.
- `run_output.txt` — captured real output from `simulate.py`.

### Design note

This project started as a job-to-be-done analysis: the ordinary framing
("loan processing takes 30 minutes") looks like a pure speed problem,
but the real job underneath it is protecting a sale from decision
decay while the customer waits. The one piece of already-collected,
currently-unused data that closes that gap for a meaningful segment of
applicants is the lender's own repayment history on repeat customers —
today buried behind a manual review step that treats every applicant,
new or returning, identically. InstaTrust is the working version of
that reframing.
