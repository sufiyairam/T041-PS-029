import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)

import unittest
from decimal import Decimal
from loader import load_employees, load_cost_centres
from pipeline import validate_all
from approvals import build_chain, chain_for_claim

claims, results = validate_all()
emp = load_employees()
cc = load_cost_centres()


def ids(chain):
    return [a for a, _ in chain]


def real(claim_id):
    return ids(chain_for_claim(claims[claim_id], results, emp, cc))


class TestChain(unittest.TestCase):

    # ---- amount boundaries (EMP-019: manager EMP-009, CC head EMP-004) ----
    def test_exactly_10000_manager_only(self):                       # CLM-026
        self.assertEqual(real("CLM-026"), ["EMP-009"])

    def test_10000_01_adds_cc_head(self):
        self.assertEqual(ids(build_chain("EMP-019", Decimal("10000.01"), False, False, emp, cc)),
                         ["EMP-009", "EMP-004"])

    def test_exactly_50000_no_finance_controller(self):              # CLM-012
        self.assertEqual(real("CLM-012"), ["EMP-010", "EMP-005"])

    def test_50000_01_adds_finance_controller(self):
        self.assertEqual(ids(build_chain("EMP-020", Decimal("50000.01"), False, False, emp, cc)),
                         ["EMP-010", "EMP-005", "EMP-002"])

    def test_big_real_claim_has_finance_controller(self):            # CLM-018
        self.assertEqual(real("CLM-018"), ["EMP-010", "EMP-005", "EMP-002"])

    # ---- exceptions ----
    def test_chain_uses_claimed_total_clm022(self):                  # claimed 54,200, payable 44,400
        self.assertEqual(real("CLM-022"), ["EMP-001", "EMP-002"])     # matches commands.txt

    def test_exception_adds_e5_even_on_small_claim(self):            # CLM-013, total 1,640
        self.assertEqual(real("CLM-013"), ["EMP-006", "EMP-001"])

    def test_exception_on_bigger_claim(self):                        # CLM-001, matches commands.txt
        self.assertEqual(real("CLM-001"), ["EMP-006", "EMP-003", "EMP-001"])

    def test_finance_controller_already_counts_as_e5(self):
        chain = build_chain("EMP-020", Decimal("60000"), True, False, emp, cc)
        self.assertEqual(ids(chain), ["EMP-010", "EMP-005", "EMP-002"])

    # ---- duplicates and own claim ----
    def test_manager_who_is_also_cc_head_appears_once(self):         # CLM-031 (EMP-004 is both)
        self.assertEqual(real("CLM-031"), ["EMP-004"])

    def test_claimant_is_never_in_own_chain(self):
        for cid, claim in claims.items():
            self.assertNotIn(claim["employee_id"], real(cid))

    def test_no_duplicate_people_in_any_chain(self):
        for cid in claims:
            chain = real(cid)
            self.assertEqual(len(chain), len(set(chain)))

    # ---- more than 10 attendees ----
    def test_big_group_needs_e4_added_when_chain_has_none(self):
        # EMP-011: manager EMP-006 (E3). Small claim, so no CC head. E4 is EMP-003.
        chain = build_chain("EMP-011", Decimal("5000"), False, True, emp, cc)
        self.assertEqual(ids(chain), ["EMP-006", "EMP-003"])

    def test_big_group_e4_already_in_chain_adds_nothing(self):       # manager is E4
        chain = build_chain("EMP-008", Decimal("5000"), False, True, emp, cc)
        self.assertEqual(ids(chain), ["EMP-004"])

    def test_every_claim_has_a_chain(self):
        for cid in claims:
            self.assertGreaterEqual(len(real(cid)), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
