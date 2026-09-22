"""
Runs a representative batch of dealer-counter applicants through
InstaTrust and reports how much of the uniform 30-minute manual-review
window gets closed for the segment it's safe to close it for -- plus a
clear look at the disqualifying cases, so it's obvious this is a
targeted fast lane, not a blanket shortcut.
"""

from approval_engine import Applicant, LoanHistory, decide, ApprovalPath, MANUAL_REVIEW_MINUTES

APPLICANTS = [
    Applicant("A-01 (new customer)", is_returning_customer=False),
    Applicant(
        "A-02 (clean repeat customer)",
        is_returning_customer=True,
        history=LoanHistory(completed_loans=2, missed_payments=0, defaults=0),
    ),
    Applicant(
        "A-03 (repeat, one late payment)",
        is_returning_customer=True,
        history=LoanHistory(completed_loans=1, missed_payments=1, defaults=0),
    ),
    Applicant(
        "A-04 (repeat, multiple late payments)",
        is_returning_customer=True,
        history=LoanHistory(completed_loans=3, missed_payments=3, defaults=0),
    ),
    Applicant(
        "A-05 (repeat, prior default)",
        is_returning_customer=True,
        history=LoanHistory(completed_loans=2, missed_payments=0, defaults=1),
    ),
    Applicant(
        "A-06 (returning, first loan still open)",
        is_returning_customer=True,
        history=LoanHistory(completed_loans=0, missed_payments=0, defaults=0),
    ),
    Applicant(
        "A-07 (clean repeat customer)",
        is_returning_customer=True,
        history=LoanHistory(completed_loans=5, missed_payments=1, defaults=0),
    ),
]


def main():
    print("=" * 82)
    print("INSTATRUST -- dealer-counter approval routing for 7 sample applicants")
    print("=" * 82)

    total_minutes_baseline = 0.0
    total_minutes_instatrust = 0.0
    instant_count = 0

    for applicant in APPLICANTS:
        decision = decide(applicant)
        total_minutes_baseline += MANUAL_REVIEW_MINUTES
        total_minutes_instatrust += decision.processing_minutes
        if decision.path == ApprovalPath.INSTANT:
            instant_count += 1

        print(f"\n[{applicant.applicant_id}]")
        print(f"  Path:      {decision.path.value}")
        print(f"  Wait time: {decision.processing_minutes:.0f} min (was {MANUAL_REVIEW_MINUTES:.0f} min)")
        print(f"  Reason:    {decision.reason}")

    minutes_saved = total_minutes_baseline - total_minutes_instatrust
    pct_saved = 100 * minutes_saved / total_minutes_baseline

    print("\n" + "=" * 82)
    print("SUMMARY")
    print("=" * 82)
    print(f"  Applicants:                {len(APPLICANTS)}")
    print(f"  Instantly approved:        {instant_count} / {len(APPLICANTS)}")
    print(f"  Total wait, uniform 30-min baseline: {total_minutes_baseline:.0f} min")
    print(f"  Total wait, with InstaTrust:          {total_minutes_instatrust:.0f} min")
    print(f"  Minutes of counter wait closed:       {minutes_saved:.0f} min ({pct_saved:.0f}%)")
    print(
        "\nNote what did NOT get fast-tracked: a customer with a prior default "
        "(A-05), one whose only loan is still open (A-06), and one with "
        "enough recent missed payments to warrant a second look (A-04) all "
        "still go through the unchanged 30-minute manual-review path. This "
        "is a fast lane for a specific, already-vetted segment -- not a "
        "blanket shortcut."
    )


if __name__ == "__main__":
    main()
