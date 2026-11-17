import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)

import unittest
from loader import load_claims, load_fx_rates
from rules import convert_to_inr, new_result, check_timeliness, check_receipts

claims = load_claims()
fx = load_fx_rates()


def results_for(claim_id):
    claim = claims[claim_id]
    results = []
    for line in claim["lines"]:
        inr, rate = convert_to_inr(line, fx)
        results.append(new_result(line, inr, rate))
    return claim, results


class TestEasyRules(unittest.TestCase):

    def test_day_60_allowed_day_61_exception(self):          # CLM-013
        claim, results = results_for("CLM-013")
        for r, line in zip(results, claim["lines"]):
            check_timeliness(r, line, claim)
        self.assertEqual(results[0]["decision"], "ALLOWED")    # day 60
        self.assertEqual(results[1]["decision"], "EXCEPTION")  # day 61
        self.assertEqual(results[1]["rule_ids"], ["BR-05"])

    def test_fourth_missing_receipt_of_500_rejected(self):   # CLM-027
        claim, results = results_for("CLM-027")
        check_receipts(results, claim["lines"])
        decisions = [r["decision"] for r in results]
        self.assertEqual(decisions[2:5], ["ALLOWED", "ALLOWED", "ALLOWED"])  # lines 3,4,5
        self.assertEqual(decisions[5:7], ["REJECTED", "REJECTED"])           # lines 6 (Rs 500.00), 7

    def test_per_diem_needs_no_receipt(self):                # CLM-001
        claim, results = results_for("CLM-001")
        check_receipts(results, claim["lines"])
        per_diems = [r for r in results if r["category"] == "PER_DIEM"]
        self.assertTrue(all(r["decision"] == "ALLOWED" for r in per_diems))

    def test_every_claim_runs_without_error(self):
        for cid in claims:
            claim, results = results_for(cid)
            check_receipts(results, claim["lines"])
            for r, line in zip(results, claim["lines"]):
                check_timeliness(r, line, claim)


if __name__ == "__main__":
    unittest.main(verbosity=2)
