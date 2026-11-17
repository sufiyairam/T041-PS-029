import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from decimal import Decimal
from loader import load_claims, load_fx_rates
from rules import convert_to_inr

claims = load_claims()
fx = load_fx_rates()


class TestMoney(unittest.TestCase):

    def test_rupees_stay_same(self):
        line = claims["CLM-001"]["lines"][0]          # TRAIN 1450 INR
        self.assertEqual(convert_to_inr(line, fx), (Decimal("1450.00"), Decimal("1")))

    def test_card_rate_exactly_2_percent_is_used(self):
        # CLM-018 line 7: HOTEL 720 USD, card 85.17, policy 83.50 -> exactly 2.00%
        line = claims["CLM-018"]["lines"][6]
        inr, rate = convert_to_inr(line, fx)
        self.assertEqual(rate, Decimal("85.17"))
        self.assertEqual(inr, Decimal("61322.40"))

    def test_card_rate_above_2_percent_uses_policy(self):
        # CLM-018 TAXI 42 USD, card 85.30 (2.16%) -> policy 83.50
        line = [l for l in claims["CLM-018"]["lines"] if l["category"] == "TAXI" and l["currency"] == "USD"][0]
        inr, rate = convert_to_inr(line, fx)
        self.assertEqual(rate, Decimal("83.50"))
        self.assertEqual(inr, Decimal("3507.00"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
