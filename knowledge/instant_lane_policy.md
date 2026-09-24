# Instant Approval Lane Policy

## Who qualifies
Returning customers with at least one completed loan, no defaults, and at most one missed payment with this lender.
Everyone else goes to the unchanged 30-minute manual underwriting review.

## Exposure step-up
Repayment history on a small loan does not prove capacity for a much larger one.
If the requested amount is more than 1.5 times the largest loan the customer has completed, route to manual review.

## Recency
Trust earned long ago is weaker evidence. If the customer's last completed loan closed more than 36 months ago, route to manual review.

## Concurrent exposure
A customer who already has an open loan with this lender can use the instant lane for at most one more concurrent loan.
With two or more open loans, route to manual review.

## Dealer risk
Instant approvals are monitored per dealer. If a dealer's instant-lane loans default above the dealer guardrail,
instant approvals at that dealer pause automatically and every application there goes to manual review until a risk manager reviews the dealer.

## Lane guardrail
The instant lane's default rate is monitored with a Wilson upper bound. If it breaches the 3% guardrail with at least 30 outcomes,
the lane tightens automatically: the allowed missed payments drop to zero.
Tightening only sends more customers to manual review, so it is safe to apply automatically. Loosening always needs a human.

## Customer ledger
Every disbursed loan, repayment, missed payment and default updates the customer's ledger.
A default recorded anywhere in the ledger removes instant eligibility immediately.
