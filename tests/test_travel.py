import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)

import unittest
from decimal import Decimal
from loader import load_claims, load_fx_rates, load_employees, load_travel_entitlements
from rules import convert_to_inr, new_result, check_travel

claims = load_claims()
fx = load_fx_rates()
employees = load_employees()
ent = load_travel_entitlements()


def travel_result(claim_id, category, override=None, flight_hours=None):
    claim = claims[claim_id]
    line = dict(next(l for l in claim["lines"] if l["category"] == category
                     and (flight_hours is None or l["flight_hours"] == flight_hours)))
    if override:
        line.update(override)
    grade = employees[claim["employee_id"]]["grade"]
    inr, rate = convert_to_inr(line, fx)
    result = new_result(line, inr, rate)
    check_travel(result, line, grade, ent)
    return result


class TestTravel(unittest.TestCase):

    def test_e4_business_on_exactly_4_hours_is_exception(self):   # CLM-022, no entitled fare
        r = travel_result("CLM-022", "FLIGHT", flight_hours="4.00")
        self.assertEqual(r["decision"], "EXCEPTION")
        self.assertEqual(r["rule_ids"], ["BR-03"])

    def test_higher_class_with_entitled_fare_is_capped(self):     # CLM-022, 3.75h, fare 7400
        r = travel_result("CLM-022", "FLIGHT", flight_hours="3.75")
        self.assertEqual(r["decision"], "CAPPED")
        self.assertEqual(r["allowed_amount"], Decimal("7400.00"))

    def test_e4_business_over_4_hours_is_allowed(self):
        r = travel_result("CLM-022", "FLIGHT", {"flight_hours": "4.01"}, flight_hours="4.00")
        self.assertEqual(r["decision"], "ALLOWED")

    def test_economy_is_allowed(self):                            # CLM-002, E2 economy
        self.assertEqual(travel_result("CLM-002", "FLIGHT")["decision"], "ALLOWED")

    def test_e1_business_is_exception(self):
        r = travel_result("CLM-002", "FLIGHT", {"travel_class": "BUSINESS"})
        self.assertEqual(r["decision"], "EXCEPTION")

    def test_train_2ac_allowed_1ac_exception_for_e2(self):        # CLM-001, E2
        self.assertEqual(travel_result("CLM-001", "TRAIN")["decision"], "ALLOWED")
        self.assertEqual(travel_result("CLM-001", "TRAIN", {"travel_class": "1AC"})["decision"], "EXCEPTION")


if __name__ == "__main__":
    unittest.main(verbosity=2)
