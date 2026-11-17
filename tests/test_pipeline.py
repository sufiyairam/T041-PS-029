import sys, os, csv
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)

import unittest
from decimal import Decimal
from pipeline import validate_all, write_line_decisions

claims, results = validate_all()


def line(claim_id, category, nth=0):
    """nth line of that category in the claim (line_no is not unique in the data)."""
    found = [results[(claim_id, pos)] for pos, l in enumerate(claims[claim_id]["lines"])
             if l["category"] == category]
    return found[nth]


class TestPlantedScenarios(unittest.TestCase):

    def test_280_lines(self):
        self.assertEqual(len(results), 280)

    def test_hotel_exactly_150_percent(self):                       # CLM-015
        r = line("CLM-015", "HOTEL")
        self.assertEqual((r["decision"], r["rule_ids"]), ("EXCEPTION", ["BR-01"]))
        self.assertEqual(r["taxable_amount"], Decimal("4500.00"))

    def test_day_60_and_61(self):                                   # CLM-013
        self.assertEqual(line("CLM-013", "TAXI", 0)["decision"], "ALLOWED")
        self.assertEqual(line("CLM-013", "TAXI", 1)["decision"], "EXCEPTION")

    def test_rs0_meal_per_diem(self):                               # CLM-021
        self.assertEqual(line("CLM-021", "PER_DIEM", 0)["decision"], "ALLOWED")

    def test_flight_exactly_4_hours_e4(self):                       # CLM-022
        self.assertEqual(line("CLM-022", "FLIGHT", 0)["decision"], "EXCEPTION")
        r = line("CLM-022", "FLIGHT", 1)
        self.assertEqual((r["decision"], r["allowed_amount"]), ("CAPPED", Decimal("7400.00")))

    def test_fourth_missing_receipt(self):                          # CLM-027
        decisions = [results[("CLM-027", pos)]["decision"]
                     for pos, l in enumerate(claims["CLM-027"]["lines"])
                     if l["receipt"] == "false"]
        self.assertEqual(decisions, ["ALLOWED"] * 3 + ["REJECTED"] * 2)

    def test_card_rate_exactly_2_percent(self):                     # CLM-018
        r = line("CLM-018", "HOTEL")
        self.assertEqual((r["rate_used"], r["amount_inr"]), (Decimal("85.17"), Decimal("61322.40")))
        taxi = line("CLM-018", "TAXI")
        self.assertEqual(taxi["rate_used"], Decimal("83.50"))

    def test_duplicate_and_vendor_flag(self):                       # CLM-019 / CLM-006 / CLM-008
        self.assertEqual(line("CLM-019", "MEAL")["decision"], "REJECTED")
        self.assertIn("DUPLICATE_VENDOR_FLAG", line("CLM-006", "TAXI", 0)["flags"])

    def test_clm031(self):
        self.assertEqual(line("CLM-031", "TEAM_MEAL", 0)["decision"], "ALLOWED")
        self.assertIn("NEEDS_E4_APPROVAL", line("CLM-031", "TEAM_MEAL", 0)["flags"])
        self.assertEqual(line("CLM-031", "ALCOHOL")["decision"], "REJECTED")
        self.assertEqual(line("CLM-031", "CLIENT_ENTERTAINMENT")["decision"], "ALLOWED")
        self.assertEqual(line("CLM-031", "TEAM_MEAL", 1)["decision"], "REJECTED")

    def test_output_file(self):
        path = write_line_decisions(claims, results)
        rows = list(csv.DictReader(open(path)))
        self.assertEqual(len(rows), 280)
        self.assertEqual(list(rows[0].keys()), ["claim_id", "line_no", "category", "amount_inr", "rate_used",
                                                "decision", "allowed_amount", "rule_ids", "flags", "taxable_amount"])

    def test_output_order_matches_input_file(self):
        out = [(r["claim_id"], r["line_no"], r["category"]) for r in
               csv.DictReader(open(write_line_decisions(claims, results)))]
        original = [(r["claim_id"], r["line_no"], r["category"]) for r in
                    csv.DictReader(open("data/claim_lines.csv"))]
        self.assertEqual(out, original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
