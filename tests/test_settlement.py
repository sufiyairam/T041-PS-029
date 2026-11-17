import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)

import csv
import unittest
from decimal import Decimal
from workflow import run_workflow
from settlement import settle, build_settlement_rows, write_claim_settlement, SETTLEMENT_COLUMNS

ENGINE = run_workflow()
ROWS = {r["claim_id"]: r for r in build_settlement_rows(ENGINE)}


class TestSettleFunction(unittest.TestCase):

    def test_approved_more_than_advance_pays_difference(self):
        self.assertEqual(settle("APPROVED", Decimal("17160"), Decimal("10000")),
                         (Decimal("0.00"), Decimal("7160.00")))

    def test_approved_exactly_equal_to_advance_pays_nothing_recovers_nothing(self):
        self.assertEqual(settle("APPROVED", Decimal("10000"), Decimal("10000")),
                         (Decimal("0.00"), Decimal("0.00")))

    def test_advance_larger_than_claim_recovers_the_rest(self):
        self.assertEqual(settle("APPROVED", Decimal("5014"), Decimal("40000")),
                         (Decimal("34986.00"), Decimal("0.00")))

    def test_no_advance(self):
        self.assertEqual(settle("APPROVED", Decimal("1640"), Decimal("0")),
                         (Decimal("0.00"), Decimal("1640.00")))

    def test_rejected_claim_recovers_whole_advance(self):
        self.assertEqual(settle("REJECTED", Decimal("0"), Decimal("10000")),
                         (Decimal("10000.00"), Decimal("0.00")))

    def test_returned_claim_is_not_settled(self):
        self.assertEqual(settle("RETURNED", Decimal("0"), Decimal("10000")),
                         (Decimal("0.00"), Decimal("0.00")))


class TestSettlementRows(unittest.TestCase):

    def test_clm029_advance_bigger_than_claim(self):                 # README scenario
        r = ROWS["CLM-029"]
        self.assertEqual(r["approved_total_inr"], "5014.00")
        self.assertEqual(r["advance_amount"], "40000.00")
        self.assertEqual(r["advance_recovered_from_salary"], "34986.00")
        self.assertEqual(r["net_payout"], "0.00")

    def test_clm009_advance_netted_first(self):                      # claimed 23660, payable 17160, advance 10000
        r = ROWS["CLM-009"]
        self.assertEqual(r["approved_total_inr"], "17160.00")
        self.assertEqual(r["net_payout"], "7160.00")
        self.assertEqual(r["advance_recovered_from_salary"], "0.00")

    def test_clm001_hotel_exception_is_taxable(self):                # hotel Rs 9,656, cap 2 x 3,500
        r = ROWS["CLM-001"]
        self.assertEqual(r["taxable_total_inr"], "2656.00")
        self.assertEqual(r["final_state"], "APPROVED")
        self.assertEqual(r["net_payout"], r["approved_total_inr"])    # no advance: taxable is still paid

    def test_rejected_claim_has_no_approved_or_taxable_amount(self):  # CLM-004
        r = ROWS["CLM-004"]
        self.assertEqual((r["approved_total_inr"], r["taxable_total_inr"], r["net_payout"]),
                         ("0.00", "0.00", "0.00"))
        self.assertEqual(r["advance_recovered_from_salary"], "10000.00")
        self.assertEqual(r["pay_by_date"], "")

    def test_returned_claim_clm013(self):
        r = ROWS["CLM-013"]
        self.assertEqual(r["final_state"], "RETURNED")
        self.assertEqual(r["net_payout"], "0.00")
        self.assertEqual(r["final_approval_at"], "")

    def test_pay_by_date_skips_weekend_and_holiday(self):            # CLM-012 approved Fri 11 Sep 16:20
        r = ROWS["CLM-012"]
        self.assertEqual(r["final_approval_at"], "2026-09-11 16:20:00")
        self.assertEqual(r["pay_by_date"], "2026-09-21")             # 14 Sep is Ganesh Chaturthi

    def test_every_claim_has_a_row(self):
        self.assertEqual(len(ROWS), 40)

    def test_file_has_correct_columns(self):
        path = write_claim_settlement(ENGINE)
        rows = list(csv.DictReader(open(path)))
        self.assertEqual(list(rows[0].keys()), SETTLEMENT_COLUMNS)
        self.assertEqual(len(rows), 40)

    def test_paid_never_exceeds_approved(self):
        for r in ROWS.values():
            self.assertLessEqual(Decimal(r["net_payout"]), Decimal(r["approved_total_inr"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
