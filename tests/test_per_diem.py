import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)

import unittest
from decimal import Decimal
from loader import load_claims, load_fx_rates, load_city_tiers, load_per_diem
from rules import (convert_to_inr, new_result, check_per_diem, lines_for_meal_check,
                   compute_taxable_amount)

claims = load_claims()
fx = load_fx_rates()
tiers = load_city_tiers()
rates = load_per_diem()


def per_diem_result(claim_id, date, override=None, hours_away=None, rate_table=None):
    claim = claims[claim_id]
    # NOTE: line_no is not unique in the sample data (CLM-021 has two line 5s),
    # so we find the line by category + date.
    line = dict(next(l for l in claim["lines"]
                     if l["category"] == "PER_DIEM" and l["expense_date"] == date
                     and (hours_away is None or l["hours_away"] == hours_away)))
    if override:
        line.update(override)
    # all lines of the same claim on the same date (see PER_DIEM_MEAL_SCOPE in rules.py)
    same_day = lines_for_meal_check(claims, claim, line)
    inr, rate = convert_to_inr(line, fx)
    result = new_result(line, inr, rate)
    check_per_diem(result, line, tiers, rate_table or rates, same_day)
    result["taxable_amount"] = compute_taxable_amount(result)
    return result


class TestPerDiem(unittest.TestCase):

    def test_normal_per_diem_allowed(self):                  # CLM-001 tier 2, Rs 750
        self.assertEqual(per_diem_result("CLM-001", claims["CLM-001"]["lines"][3]["expense_date"])["decision"], "ALLOWED")

    def test_per_diem_with_real_meal_same_day_rejected(self): # CLM-006: per diem 1000 + meal 780
        r = per_diem_result("CLM-006", "2026-08-25")
        self.assertEqual(r["decision"], "REJECTED")
        self.assertEqual(r["rule_ids"], ["BR-02"])

    def test_rs0_meal_does_not_block_per_diem(self):         # CLM-021 line 5 + line 6 (Rs 0)
        r = per_diem_result("CLM-021", "2026-09-15")
        self.assertEqual(r["decision"], "ALLOWED")

    def test_over_a_full_day_rate_is_an_exception_with_taxable_excess(self):   # tier 1: 1,200 vs 1,000
        r = per_diem_result("CLM-021", "2026-09-15", {"amount": "1200.00"})
        self.assertEqual(r["decision"], "EXCEPTION")
        self.assertEqual(r["rule_ids"], ["BR-02"])
        self.assertEqual(r["allowed_amount"], Decimal("1200.00"))      # payable if E5 approves
        self.assertEqual(r["cap_excess"], Decimal("200.00"))
        self.assertEqual(r["taxable_amount"], Decimal("200.00"))       # above Rs 1,000: taxable

    def test_exactly_the_rate_is_allowed_and_not_taxable(self):
        r = per_diem_result("CLM-021", "2026-09-15", {"amount": "1000.00"})
        self.assertEqual((r["decision"], r["taxable_amount"]), ("ALLOWED", Decimal("0.00")))

    def test_tier2_over_rate_taxes_everything_above_the_cap(self):            # tier 2: 1,200 vs 750
        date = claims["CLM-001"]["lines"][3]["expense_date"]                  # a tier-2 per diem of 750
        r = per_diem_result("CLM-001", date, {"amount": "1200.00"})
        self.assertEqual(r["decision"], "EXCEPTION")
        self.assertEqual(r["taxable_amount"], Decimal("450.00"))               # 1,200 - 750 (includes the part above 1,000)

    def test_short_travel_day_full_claim_is_capped_not_exception(self):       # 1,000 on a 6-hour day -> 500
        r = per_diem_result("CLM-021", "2026-09-15", {"hours_away": "6"})
        self.assertEqual(r["decision"], "CAPPED")
        self.assertEqual(r["allowed_amount"], Decimal("500.00"))
        self.assertEqual(r["taxable_amount"], Decimal("0.00"))

    def test_domestic_above_1000_clause_works_if_the_policy_table_allows_it(self):
        bigger = dict(rates); bigger["TIER1"] = 1200.0                         # pretend policy pays 1,200
        r = per_diem_result("CLM-021", "2026-09-15", {"amount": "1200.00"}, rate_table=bigger)
        self.assertEqual(r["decision"], "ALLOWED")
        self.assertEqual(r["taxable_amount"], Decimal("200.00"))               # still taxable: above Rs 1,000

    def test_rejected_per_diem_is_never_taxable(self):                        # CLM-006 clash with a meal
        r = per_diem_result("CLM-006", "2026-08-25", {"amount": "1500.00"})
        self.assertEqual(r["decision"], "REJECTED")
        self.assertEqual(r["taxable_amount"], Decimal("0.00"))

    def test_international_half_day_is_capped_to_25_usd(self):
        # the one international line with hours_away = 6.5
        found = [(c["claim_id"], l["expense_date"]) for c in claims.values()
                 for l in c["lines"] if l["category"] == "PER_DIEM" and l["hours_away"] == "6.5"]
        self.assertEqual(len(found), 1)
        r = per_diem_result(found[0][0], found[0][1], hours_away="6.5")
        self.assertEqual(r["decision"], "CAPPED")
        self.assertEqual(r["allowed_amount"], Decimal("25") * r["rate_used"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
