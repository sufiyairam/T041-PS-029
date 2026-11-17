import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)

import unittest
from decimal import Decimal
from loader import load_claims, load_fx_rates, load_employees
from rules import convert_to_inr, new_result, check_team_meal

claims = load_claims()
fx = load_fx_rates()
employees = load_employees()


def meal_result(claim_id, category, text_in_description="", override=None, grade=None):
    claim = claims[claim_id]
    line = dict(next(l for l in claim["lines"] if l["category"] == category
                     and text_in_description in l["description"]))
    if override:
        line.update(override)
    g = grade or employees[claim["employee_id"]]["grade"]
    inr, rate = convert_to_inr(line, fx)
    result = new_result(line, inr, rate)
    check_team_meal(result, line, g, employees)
    return result


class TestTeamMeal(unittest.TestCase):

    def test_11_attendees_at_1150_allowed_but_needs_e4(self):        # CLM-031
        r = meal_result("CLM-031", "TEAM_MEAL", "11 attendees")
        self.assertEqual(r["decision"], "ALLOWED")
        self.assertIn("NEEDS_E4_APPROVAL", r["flags"])

    def test_alcohol_category_rejected(self):                         # CLM-031
        r = meal_result("CLM-031", "ALCOHOL")
        self.assertEqual(r["decision"], "REJECTED")
        self.assertEqual(r["rule_ids"], ["BR-07"])

    def test_client_entertainment_with_drinks_by_e3_allowed(self):    # CLM-031
        self.assertEqual(meal_result("CLM-031", "CLIENT_ENTERTAINMENT")["decision"], "ALLOWED")

    def test_client_entertainment_with_drinks_by_e2_rejected(self):
        r = meal_result("CLM-031", "CLIENT_ENTERTAINMENT", grade="E2")
        self.assertEqual(r["decision"], "REJECTED")

    def test_attendee_not_employee_or_client_rejected(self):          # CLM-031 'Vikram (friend)'
        r = meal_result("CLM-031", "TEAM_MEAL", "Attendee not an employee")
        self.assertEqual(r["decision"], "REJECTED")

    def test_over_1200_per_head_is_capped(self):                      # CLM-002: 5500 / 4 heads
        r = meal_result("CLM-002", "TEAM_MEAL")
        self.assertEqual(r["decision"], "CAPPED")
        self.assertEqual(r["allowed_amount"], Decimal("4800.00"))

    def test_exactly_1200_per_head_is_allowed(self):                  # 4 heads x 1200 = 4800
        r = meal_result("CLM-002", "TEAM_MEAL", override={"amount": "4800.00"})
        self.assertEqual(r["decision"], "ALLOWED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
