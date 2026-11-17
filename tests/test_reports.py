import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)

import csv
import unittest
from decimal import Decimal
from workflow import run_workflow
from settlement import build_settlement_rows
from reports import (month_range, months_from_requests, build_cost_centre_rows,
                     write_cost_centre_report, REPORT_COLUMNS)

ENGINE = run_workflow()
MONTHS = months_from_requests(ENGINE)
ROWS = build_cost_centre_rows(ENGINE, MONTHS)


def row(cc, month):
    return next(r for r in ROWS if r["cost_centre"] == cc and r["month"] == month)


class TestMonthRange(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(month_range("2026-09", "2026-10"), ["2026-09", "2026-10"])

    def test_across_year_end(self):
        self.assertEqual(month_range("2026-11", "2027-02"), ["2026-11", "2026-12", "2027-01", "2027-02"])

    def test_single_month(self):
        self.assertEqual(month_range("2026-10", "2026-10"), ["2026-10"])


class TestReport(unittest.TestCase):

    def test_months_come_from_print_report_command(self):
        self.assertEqual(MONTHS, ["2026-09", "2026-10"])

    def test_one_row_per_cost_centre_per_month(self):
        self.assertEqual(len(ROWS), 4 * 2)
        self.assertEqual(len({(r["cost_centre"], r["month"]) for r in ROWS}), 8)

    def test_claims_are_not_lost_or_double_counted(self):
        in_range = [cid for cid, s in ENGINE.states.items()
                    if s["submitted_at"].strftime("%Y-%m") in MONTHS]
        self.assertEqual(sum(r["claims_count"] for r in ROWS), len(in_range))
        self.assertEqual(len(in_range), 35)          # CLM-001..005 were submitted in August

    def test_approved_total_matches_settlement_file(self):
        settlement = {r["claim_id"]: r for r in build_settlement_rows(ENGINE)}
        expected = sum(Decimal(settlement[cid]["approved_total_inr"]) for cid, s in ENGINE.states.items()
                       if s["submitted_at"].strftime("%Y-%m") in MONTHS)
        self.assertEqual(sum(Decimal(r["approved_total_inr"]) for r in ROWS), expected)

    def test_taxable_total_matches_settlement_file(self):
        settlement = {r["claim_id"]: r for r in build_settlement_rows(ENGINE)}
        expected = sum(Decimal(settlement[cid]["taxable_total_inr"]) for cid, s in ENGINE.states.items()
                       if s["submitted_at"].strftime("%Y-%m") in MONTHS)
        self.assertEqual(sum(Decimal(r["taxable_total_inr"]) for r in ROWS), expected)

    def test_august_claims_are_left_out(self):
        # CLM-004 (rejected, Rs 21,553, submitted 29 Aug) must not appear in Sep or Oct
        self.assertNotIn("21553.00", [r["rejected_total_inr"] for r in ROWS])

    def test_rejected_claim_counts_whole_claim_as_rejected(self):   # CLM-018, EMP-015 (claimed 134,812)
        cc = ENGINE.employees["EMP-015"]["cost_centre"]
        month = ENGINE.states["CLM-018"]["submitted_at"].strftime("%Y-%m")
        self.assertGreaterEqual(Decimal(row(cc, month)["rejected_total_inr"]), Decimal("134812.00"))

    def test_exception_total_is_paid_exception_lines(self):         # CLM-011 hotel exception Rs 13,712 (approved)
        cc = ENGINE.employees["EMP-021"]["cost_centre"]
        month = ENGINE.states["CLM-011"]["submitted_at"].strftime("%Y-%m")
        self.assertGreaterEqual(Decimal(row(cc, month)["exception_total_inr"]), Decimal("13712.00"))

    def test_exception_never_more_than_approved(self):
        for r in ROWS:
            self.assertLessEqual(Decimal(r["exception_total_inr"]), Decimal(r["approved_total_inr"]))

    def test_file_columns(self):
        path = write_cost_centre_report(ENGINE)
        rows = list(csv.DictReader(open(path)))
        self.assertEqual(list(rows[0].keys()), REPORT_COLUMNS)
        self.assertEqual(len(rows), 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
