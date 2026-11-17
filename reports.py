"""
reports.py  -  STEP 10: monthly cost-centre report   (PRINT_REPORT command)

One row for every cost centre for every month in the requested range.

How each column is worked out (for claims whose FIRST SUBMIT was in that month,
and whose claimant belongs to that cost centre):
  claims_count        number of claims submitted
  approved_total_inr  money payable on claims that ended APPROVED
  exception_total_inr money paid on EXCEPTION lines of claims that ended APPROVED
                      (spend beyond policy that a senior approver agreed to)
  rejected_total_inr  money refused: rule-rejected lines in every claim, plus
                      the whole claimed total of claims the approver REJECTED
  taxable_total_inr   taxable perquisite on claims that ended APPROVED
"""
import csv
import os
from decimal import Decimal

from rules import money
from settlement import build_settlement_rows
from paths import output_folder

ZERO = Decimal("0.00")
REPORT_COLUMNS = ["cost_centre", "month", "claims_count", "approved_total_inr",
                  "exception_total_inr", "rejected_total_inr", "taxable_total_inr"]


def month_range(from_month, to_month):
    """'2026-09','2026-10' -> ['2026-09', '2026-10']  (works across a year end too)"""
    year, month = int(from_month[:4]), int(from_month[5:7])
    end_year, end_month = int(to_month[:4]), int(to_month[5:7])
    months = []
    while (year, month) <= (end_year, end_month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return months


def months_from_requests(engine):
    """All months named by PRINT_REPORT commands. If there were none, use every month
    in which a claim was submitted."""
    months = set()
    for _, from_month, to_month in engine.report_requests:
        months.update(month_range(from_month, to_month))
    if not months:
        months = {s["submitted_at"].strftime("%Y-%m") for s in engine.states.values()}
    return sorted(months)


def build_cost_centre_rows(engine, months):
    settlement = {r["claim_id"]: r for r in build_settlement_rows(engine)}
    totals = {(cc, m): {"count": 0, "approved": ZERO, "exception": ZERO, "rejected": ZERO, "taxable": ZERO}
              for cc in engine.cost_centres for m in months}

    for claim_id, claim in engine.claims.items():
        state = engine.states.get(claim_id)
        if state is None:
            continue                                    # never submitted
        month = state["submitted_at"].strftime("%Y-%m")
        cost_centre = engine.employees[claim["employee_id"]]["cost_centre"]
        bucket = totals.get((cost_centre, month))
        if bucket is None:
            continue                                    # month not in the requested range

        results = [engine.results[(claim_id, pos)] for pos in range(len(claim["lines"]))]
        bucket["count"] += 1

        if state["state"] == "APPROVED":
            row = settlement[claim_id]
            bucket["approved"] += Decimal(row["approved_total_inr"])
            bucket["taxable"] += Decimal(row["taxable_total_inr"])
            bucket["exception"] += sum((r["allowed_amount"] for r in results if r["decision"] == "EXCEPTION"), ZERO)

        if state["state"] == "REJECTED":
            bucket["rejected"] += sum((r["amount_inr"] for r in results), ZERO)     # the whole claim
        else:
            bucket["rejected"] += sum((r["amount_inr"] for r in results if r["decision"] == "REJECTED"), ZERO)

    rows = []
    for cost_centre in engine.cost_centres:             # order of cost_centres.csv
        for month in months:
            b = totals[(cost_centre, month)]
            rows.append({"cost_centre": cost_centre, "month": month, "claims_count": b["count"],
                         "approved_total_inr": f'{money(b["approved"]):.2f}',
                         "exception_total_inr": f'{money(b["exception"]):.2f}',
                         "rejected_total_inr": f'{money(b["rejected"]):.2f}',
                         "taxable_total_inr": f'{money(b["taxable"]):.2f}'})
    return rows


def write_cost_centre_report(engine, path=None):
    os.makedirs(output_folder(), exist_ok=True)
    path = path or os.path.join(output_folder(), "cost_centre_report.csv")
    rows = build_cost_centre_rows(engine, months_from_requests(engine))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REPORT_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return path
