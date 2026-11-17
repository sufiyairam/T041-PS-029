import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)

import unittest
from decimal import Decimal
from loader import (load_claims, load_fx_rates, load_employees,
                    load_city_tiers, load_hotel_caps)
from rules import convert_to_inr, new_result, check_hotel

claims = load_claims()
fx = load_fx_rates()
employees = load_employees()
tiers = load_city_tiers()
caps = load_hotel_caps()


def hotel_result(claim_id, line_index, override=None):
    claim = claims[claim_id]
    line = dict(claim["lines"][line_index])
    if override:
        line.update(override)
    grade = employees[claim["employee_id"]]["grade"]
    inr, rate = convert_to_inr(line, fx)
    result = new_result(line, inr, rate)
    check_hotel(result, line, grade, tiers, caps)
    return result


class TestHotel(unittest.TestCase):

    def test_exactly_150_percent_is_exception(self):       # CLM-015, 13500 / 2 nights, cap 4500
        r = hotel_result("CLM-015", 5)
        self.assertEqual(r["decision"], "EXCEPTION")
        self.assertEqual(r["rule_ids"], ["BR-01"])
        self.assertEqual(r["cap_excess"], Decimal("4500.00"))   # 13500 - 2*4500

    def test_just_above_150_percent_is_rejected(self):
        r = hotel_result("CLM-015", 5, {"amount": "13500.01"})
        self.assertEqual(r["decision"], "REJECTED")
        self.assertEqual(r["allowed_amount"], Decimal("0.00"))

    def test_within_cap_is_allowed(self):                  # CLM-003: E1, 7737 / 3 nights, cap 3000
        self.assertEqual(hotel_result("CLM-003", 1)["decision"], "ALLOWED")

    def test_exactly_at_cap_is_allowed(self):              # 2 nights x 4500 = 9000
        r = hotel_result("CLM-015", 5, {"amount": "9000.00"})
        self.assertEqual(r["decision"], "ALLOWED")

    def test_international_hotel_has_no_cap(self):         # CLM-018 San Francisco
        r = hotel_result("CLM-018", 6)
        self.assertEqual(r["decision"], "ALLOWED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
