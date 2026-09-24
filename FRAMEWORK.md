# InstaTrust — FDE Framework Build Notes

## Part 1 — Problem Reframing

| Step | Output |
|---|---|
| Ordinary problem | "Loan processing at the dealer counter takes 30 minutes." |
| Lever 1: Data liquidity | The lender's own repayment ledger already answers the trust question for returning customers, but it sits behind a manual review queue. Per-dealer loss data exists but is never used at the counter. |
| Lever 2: Network effect | Every instant-lane outcome updates the customer's ledger, the dealer's record and the lane's guardrail. More volume means dealer fraud is caught sooner and exposure ceilings grow as customers repay larger loans. |
| Lever 3: Algorithmic leverage | "Trust for this loan, at this dealer, now": an exposure step-up (at most 1.5× the largest completed loan), recency, concurrent exposure, and a dealer circuit breaker. Each check can only move an applicant toward manual review. |
| Lever 4: First principles × JTBD | The customer's job is "lock in this purchase before I lose my nerve". The lender's job is "don't let speed become the fraud vector". Both have to hold. |
| Extraordinary problem | **Give returning customers an instant approval that is safe for the size of the loan and the dealer**, and make the lane protect itself: tighten automatically when losses rise, and loosen only with a human. |
| Rating | 4 / 5 |

## Part 2 — Design the Eval

**Outcome of intelligence**
- Instant-lane default rate stays under the 3% lane guardrail (Wilson lower bound, n ≥ 30).
- No v2 check ever moves an applicant v1 sent to manual review into the instant lane.
- A dealer with confident excess defaults is paused automatically. Small samples never pause a dealer.

**EQ(PRE)**
| Angle | Hypothesis |
|---|---|
| Causal | Past repayment of a small loan is taken as evidence of capacity for a much larger one. |
| Context | The fast lane can't see which dealer the application comes from, so a dealer-side fraud ring exploits it. |
| Consistency | The rules are fixed while the loss environment shifts. |

**EQ(POST), cheapest first**
1. Prompt: the counter message never reveals internal risk reasons. The offline template is the floor.
2. Context/retrieval: exposure step-up, recency, concurrent loans, dealer status, and policy citations.
3. Feedback: outcomes update the ledger, then the dealer circuit breaker, then the lane guardrail (auto-tighten only).

**Executable:** `python run_evals.py` runs 14 cases × 3 runs (v1 batch parity, context rules, one-way safety, dealer pause, lane tighten).

## Part 3 — Gen-4 Architecture

| Layer | What InstaTrust does |
|---|---|
| Retrieval | `knowledge/instant_lane_policy.md`. The clause behind each routing reason is cited. |
| Context | Requested amount vs largest completed loan, months since last close, open loans, dealer id and its guardrail state. |
| Memory | Per-customer ledger (loans, amounts, status, missed payments, close dates), every decision, every outcome. |
| Feedback | `POST /feedback` updates the ledger and re-checks the dealer and lane guardrails. The lane auto-tightens (missed payments allowed goes from 1 to 0). Loosening is a human action. |

The model writes the one-line counter message and never exposes risk reasons. The offline template is used without a key.

## Part 4 — Implementation Plan

| Component | Priority | Estimate | Status |
|---|---|---|---|
| Customer ledger in memory + ledger API | MVP | 0.5 day | done |
| Exposure step-up, recency, concurrency checks (one-way) | MVP | 0.5 day | done |
| Dealer circuit breaker (Wilson lower bound) | MVP | 0.25 day | done |
| Lane guardrail with auto-tighten | MVP | 0.25 day | done |
| API, Docker, CI | MVP | 0.5 day | done |
| Loan-management-system webhook for repayments | nice-to-have | 1–2 days | future |
| Bureau refresh for customers idle more than 12 months | future | 2 days | future |
| Dealer risk dashboard | nice-to-have | 1 day | future |

## Part 5 — Prove It

**Visible change** (`python simulate_learning.py`, output in `run_output_learning.txt`). The same 600 returning-customer applications run through both versions. The synthetic world has two hidden risks: customers asking for more than 1.5× their largest past loan, and a fraud ring at dealer D-13.

| After | v1 instant-lane defaults | v2 instant-lane defaults | D-13 in v2 |
|---|---|---|---|
| 200 apps | 26 / 200 (13.0%) | 4 / 100 (4.0%) | paused automatically |
| 400 apps | 46 / 400 (11.5%) | 5 / 183 (2.7%) | paused |
| 600 apps | 59 / 600 (9.8%) | **7 / 273 (2.6%)** | paused |

The trade-off is stated plainly: v2 keeps the 28-minute saving for 46% of applicants instead of 100%, and cuts instant-lane defaults by about 4×. The applicants it slows down are exactly the ones this world says are risky. An outside observer would see a fast lane that no longer leaks losses, and a dealer fraud ring shut out of the fast lane with no one writing a rule for it.
