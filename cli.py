"""
CLI entry point for InstaTrust.

Usage:
    python3 cli.py                                       # run the bundled sample batch
    python3 cli.py --returning --loans 2 --missed 0 --defaults 0
    python3 cli.py --new                                 # evaluate a new applicant
"""

import argparse

from approval_engine import Applicant, LoanHistory, decide
from simulate import main as simulate_main


def main():
    parser = argparse.ArgumentParser(description="InstaTrust: instant approval routing engine")
    parser.add_argument("--new", action="store_true", help="evaluate a brand-new applicant")
    parser.add_argument("--returning", action="store_true", help="evaluate a returning applicant")
    parser.add_argument("--loans", type=int, default=0, help="completed loans with this lender")
    parser.add_argument("--missed", type=int, default=0, help="missed (but eventually paid) payments")
    parser.add_argument("--defaults", type=int, default=0, help="loans never repaid")
    args = parser.parse_args()

    if not args.new and not args.returning:
        print("No --new/--returning given -- running the bundled sample batch instead.\n")
        simulate_main()
        return

    applicant = Applicant(
        "cli-applicant",
        is_returning_customer=args.returning,
        history=LoanHistory(completed_loans=args.loans, missed_payments=args.missed, defaults=args.defaults),
    )
    decision = decide(applicant)
    print(f"Path:      {decision.path.value}")
    print(f"Wait time: {decision.processing_minutes:.0f} min")
    print(f"Reason:    {decision.reason}")


if __name__ == "__main__":
    main()
