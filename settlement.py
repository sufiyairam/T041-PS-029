"""
settlement.py  -  STEP 9: money at the end of the claim  (BR-11 and BR-12)

For every claim we work out:
  claimed_total   everything the employee wrote on the claim
  approved_total  what we agree to pay (only if the claim ended APPROVED)
  taxable_total   the part of the approved total that is a taxable perquisite
  advance         money the employee already received before the trip
  net_payout      what we still pay
  recovered       advance the employee did not spend, taken back from salary
  pay_by_date     5 working days after the final approval
"""
import csv
import os
from decimal import Decimal

from calendar_rules import add_working_days
from rules import money
from paths import output_folder
from workflow import show_time

PAY_WITHIN_WORKING_DAYS = 5
ZERO = Decimal("0.00")

SETTLEMENT_COLUMNS = ["claim_id", "employee_id", "claimed_total_inr", "approved_total_inr",
                      "taxable_total_inr", "advance_amount", "advance_recovered_from_salary",
                      "net_payout", "final_state", "final_approval_at", "pay_by_date"]


def settle(state, approved_total, advance):
    """Return (advance_recovered_from_salary, net_payout).

    APPROVED : the advance is netted FIRST.
                 approved >= advance -> pay the difference
                 approved <  advance -> pay nothing, recover the unspent advance from salary
    REJECTED : nothing is approved, so the whole advance is recovered from salary.
    Anything else (RETURNED, still pending): the claim is still open, nothing is settled yet.
    """
    if state == "APPROVED":
        if approved_total >= advance:
            return ZERO, money(approved_total - advance)
        return money(advance - approved_total), ZERO
    if state == "REJECTED":
        return money(advance), ZERO
    return ZERO, ZERO


def build_settlement_rows(engine):
    rows = []
    for claim_id, claim in engine.claims.items():
        state_info = engine.states.get(claim_id)
        state = state_info["state"] if state_info else "NOT_SUBMITTED"
        results = [engine.results[(claim_id, pos)] for pos in range(len(claim["lines"]))]

        claimed_total = money(sum((r["amount_inr"] for r in results), ZERO))
        approved = state == "APPROVED"
        approved_total = money(sum((r["allowed_amount"] for r in results), ZERO)) if approved else ZERO
        taxable_total = money(sum((r["taxable_amount"] for r in results), ZERO)) if approved else ZERO
        advance = money(claim["advance_amount"])
        recovered, payout = settle(state, approved_total, advance)

        final_at, pay_by = "", ""
        if approved:
            final_at = show_time(state_info["final_approval_at"])
            pay_by = add_working_days(state_info["final_approval_at"].date(),
                                      PAY_WITHIN_WORKING_DAYS, engine.holidays).isoformat()

        rows.append({
            "claim_id": claim_id, "employee_id": claim["employee_id"],
            "claimed_total_inr": f"{claimed_total:.2f}", "approved_total_inr": f"{approved_total:.2f}",
            "taxable_total_inr": f"{taxable_total:.2f}", "advance_amount": f"{advance:.2f}",
            "advance_recovered_from_salary": f"{recovered:.2f}", "net_payout": f"{payout:.2f}",
            "final_state": state, "final_approval_at": final_at, "pay_by_date": pay_by,
        })
    return rows


def write_claim_settlement(engine, path=None):
    os.makedirs(output_folder(), exist_ok=True)
    path = path or os.path.join(output_folder(), "claim_settlement.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SETTLEMENT_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(build_settlement_rows(engine))
    return path
