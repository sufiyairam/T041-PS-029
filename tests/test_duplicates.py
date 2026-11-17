import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)

import unittest
from decimal import Decimal
from loader import load_claims, load_fx_rates
from rules import convert_to_inr, new_result, check_duplicates

fx = load_fx_rates()


def build_results(claims):
    out = {}
    for claim in claims.values():
        for pos, line in enumerate(claim["lines"]):
            inr, rate = convert_to_inr(line, fx)
            out[(claim["claim_id"], pos)] = new_result(line, inr, rate)
    return out


def tiny_claim(cid, emp, submitted, amounts, trip="TRP-X", vendor="V", date="2026-09-01", cat="TAXI"):
    lines = [{"claim_id": cid, "line_no": str(i + 1), "category": cat, "expense_date": date,
              "amount": a, "currency": "INR", "card_rate": "NA", "vendor": vendor}
             for i, a in enumerate(amounts)]
    return {"claim_id": cid, "employee_id": emp, "submitted_at": submitted, "trip_ref": trip, "lines": lines}


class TestDuplicates(unittest.TestCase):

    def test_sample_data_clm019_rejected_clm006_kept(self):
        claims = load_claims()
        results = build_results(claims)
        check_duplicates(claims, results)
        meal_006 = next(r for (cid, pos), r in results.items()
                        if cid == "CLM-006" and r["category"] == "MEAL")
        meal_019 = results[("CLM-019", 0)]
        self.assertEqual(meal_019["decision"], "REJECTED")
        self.assertEqual(meal_019["rule_ids"], ["BR-06"])
        self.assertEqual(meal_006["decision"], "ALLOWED")

    def test_sample_data_shared_taxi_flagged_not_rejected(self):
        claims = load_claims()
        results = build_results(claims)
        check_duplicates(claims, results)
        for cid in ("CLM-006", "CLM-008"):
            taxi = next(r for (c, pos), r in results.items()
                        if c == cid and r["category"] == "TAXI" and r["amount_inr"] == Decimal("650.00"))
            self.assertIn("DUPLICATE_VENDOR_FLAG", taxi["flags"])
            self.assertEqual(taxi["decision"], "ALLOWED")

    def test_exactly_1_rupee_apart_is_duplicate(self):
        claims = {"A": tiny_claim("A", "E1", "2026-09-01 10:00:00", ["500.00"]),
                  "B": tiny_claim("B", "E1", "2026-09-02 10:00:00", ["501.00"])}
        results = build_results(claims); check_duplicates(claims, results)
        self.assertEqual(results[("B", 0)]["decision"], "REJECTED")

    def test_1_01_rupees_apart_is_not_duplicate(self):
        claims = {"A": tiny_claim("A", "E1", "2026-09-01 10:00:00", ["500.00"]),
                  "B": tiny_claim("B", "E1", "2026-09-02 10:00:00", ["501.01"])}
        results = build_results(claims); check_duplicates(claims, results)
        self.assertEqual(results[("B", 0)]["decision"], "ALLOWED")

    def test_different_employee_is_not_a_duplicate(self):
        claims = {"A": tiny_claim("A", "E1", "2026-09-01 10:00:00", ["500.00"]),
                  "B": tiny_claim("B", "E2", "2026-09-02 10:00:00", ["500.00"])}
        results = build_results(claims); check_duplicates(claims, results)
        self.assertEqual(results[("B", 0)]["decision"], "ALLOWED")
        self.assertIn("DUPLICATE_VENDOR_FLAG", results[("B", 0)]["flags"])   # same trip, same vendor

    def test_later_line_in_same_claim_is_rejected(self):
        claims = {"A": tiny_claim("A", "E1", "2026-09-01 10:00:00", ["180.00", "180.00"])}
        results = build_results(claims); check_duplicates(claims, results)
        self.assertEqual(results[("A", 0)]["decision"], "ALLOWED")
        self.assertEqual(results[("A", 1)]["decision"], "REJECTED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
