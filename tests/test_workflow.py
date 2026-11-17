import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)

import csv
import unittest
from datetime import date
from loader import load_employees, load_cost_centres, load_holidays, load_commands_with_lines
from pipeline import validate_all
from workflow import Engine, run_workflow, write_audit_trail, AUDIT_COLUMNS
from calendar_rules import sla_deadline, breach_day, is_working_day

holidays = load_holidays()
claims_all, results_all = validate_all()
FULL = run_workflow()                       # the real commands.txt


def fresh_engine(commands):
    """Engine on the real claims, but with our own small list of commands."""
    e = Engine(claims_all, results_all, load_employees(), load_cost_centres(), holidays)
    e.run([(i + 1, c.split("|")) for i, c in enumerate(commands)])
    return e


def events(engine, claim_id):
    return [(r["event"], r["timestamp"], r["pending_approver"], r["state_after"])
            for r in engine.audit if r["claim_id"] == claim_id]


class TestCalendar(unittest.TestCase):

    def test_clm023_deadline_and_breach_land_around_holiday(self):
        start = date(2026, 9, 28)                              # Monday
        self.assertEqual(sla_deadline(start, holidays), date(2026, 10, 1))   # Thursday
        self.assertFalse(is_working_day(date(2026, 10, 2), holidays))        # Gandhi Jayanti
        self.assertEqual(breach_day(start, holidays), date(2026, 10, 5))     # next Monday

    def test_weekend_and_holiday_are_not_working_days(self):
        self.assertFalse(is_working_day(date(2026, 9, 12), holidays))        # Saturday
        self.assertFalse(is_working_day(date(2026, 9, 14), holidays))        # Ganesh Chaturthi (Monday)
        self.assertTrue(is_working_day(date(2026, 9, 15), holidays))

    def test_start_on_friday_counts_from_monday(self):
        self.assertEqual(sla_deadline(date(2026, 9, 4), holidays), date(2026, 9, 9))   # Mon, Tue, Wed 7-9


class TestRealCommands(unittest.TestCase):

    def test_peer_approval_refused_clm001(self):                         # line 4
        self.assertTrue(any(r["line_no_in_commands"] == 4 and r["claim_id"] == "CLM-001"
                            for r in FULL.rejected))

    def test_self_approval_refused_clm006(self):                         # line 19
        r = next(r for r in FULL.rejected if r["line_no_in_commands"] == 19)
        self.assertEqual(r["reason"], "SELF_APPROVAL")

    def test_only_three_commands_refused(self):
        self.assertEqual(sorted(r["line_no_in_commands"] for r in FULL.rejected), [4, 19, 57])

    def test_clm023_escalates_on_monday_5_oct_and_ems004_approves(self):
        ev = events(FULL, "CLM-023")
        self.assertEqual(ev[1], ("ESCALATE", "2026-10-05 00:00:00", "EMP-004", "PENDING_APPROVAL"))
        self.assertEqual(ev[2][0], "APPROVE")
        self.assertEqual(ev[2][3], "APPROVED")

    def test_clm035_same_person_approves_twice(self):
        ev = [e[0] for e in events(FULL, "CLM-035")]
        self.assertEqual(ev, ["SUBMIT", "ESCALATE", "APPROVE", "APPROVE"])
        self.assertEqual(FULL.states["CLM-035"]["state"], "APPROVED")

    def test_clm013_two_top_escalations_return_exception_claim(self):
        ev = events(FULL, "CLM-013")
        names = [e[0] for e in ev]
        self.assertEqual(names, ["SUBMIT", "APPROVE", "ESCALATE", "AUTO_RETURN"])
        self.assertEqual(ev[-1][3], "RETURNED")

    def test_return_then_resubmit_restarts_chain(self):                  # CLM-002
        names = [e[0] for e in events(FULL, "CLM-002")]
        self.assertEqual(names[:4], ["SUBMIT", "RETURN", "RESUBMIT", "APPROVE"])

    def test_final_states(self):
        s = {cid: st["state"] for cid, st in FULL.states.items()}
        self.assertEqual(s["CLM-004"], "REJECTED")
        self.assertEqual(s["CLM-018"], "REJECTED")
        self.assertEqual(sum(v == "APPROVED" for v in s.values()), 37)

    def test_every_claim_submitted(self):
        self.assertEqual(len(FULL.states), 40)


class TestSlaRules(unittest.TestCase):

    def test_returned_claim_clock_stops_then_fresh_sla_on_resubmit(self):
        e = fresh_engine([
            "SUBMIT|CLM-026|2026-10-05 10:00:00",
            "RETURN|CLM-026|EMP-009|2026-10-06 10:00:00|missing invoice",
            "SUBMIT|CLM-010|2026-10-26 10:00:00",                # 3 weeks later: no escalation
            "RESUBMIT|CLM-026|2026-10-26 11:00:00|fixed",
            "SUBMIT|CLM-014|2026-11-02 10:00:00",                # time passes: first breach (30 Oct) only
        ])
        names = [x[0] for x in events(e, "CLM-026")]
        self.assertEqual(names, ["SUBMIT", "RETURN", "RESUBMIT", "ESCALATE"])
        # resubmitted Mon 26 Oct: days 27, 28, 29 -> breach Fri 30 Oct
        self.assertEqual(events(e, "CLM-026")[-1][1], "2026-10-30 00:00:00")

    def test_two_top_escalations_auto_approve_claim_without_exception(self):
        e = fresh_engine([
            "SUBMIT|CLM-007|2026-09-02 12:45:00",                # chain [EMP-003]; no exception line
            "SUBMIT|CLM-010|2026-12-01 10:00:00",                # time passes
        ])
        ev = events(e, "CLM-007")
        self.assertEqual([x[0] for x in ev], ["SUBMIT", "ESCALATE", "ESCALATE", "AUTO_APPROVE"])
        self.assertEqual(ev[1][1], "2026-09-08 00:00:00")        # EMP-003 -> EMP-001
        self.assertEqual(ev[2][1], "2026-09-15 00:00:00")        # first breach at the top (9-14 is a holiday)
        self.assertEqual(ev[3][1], "2026-09-21 00:00:00")        # second breach at the top
        self.assertEqual(ev[3][3], "APPROVED")
        self.assertIsNotNone(e.states["CLM-007"]["final_approval_at"])

    def test_original_approver_cannot_act_after_escalation(self):
        e = fresh_engine([
            "SUBMIT|CLM-010|2026-09-07 11:30:00",                # chain [EMP-006]; breach 2026-09-11
            "APPROVE|CLM-010|EMP-006|2026-09-14 10:00:00|late",
        ])
        self.assertEqual(e.rejected[0]["reason"], "NOT_PENDING_APPROVER")

    def test_nothing_after_reject(self):
        e = fresh_engine([
            "SUBMIT|CLM-010|2026-09-07 11:30:00",
            "REJECT|CLM-010|EMP-006|2026-09-08 10:00:00|no",
            "APPROVE|CLM-010|EMP-006|2026-09-08 11:00:00|",
        ])
        self.assertTrue(e.rejected[0]["reason"].startswith("CLAIM_NOT_PENDING"))


class TestOutputFile(unittest.TestCase):

    def test_audit_trail_file_columns_and_row_count(self):
        path = write_audit_trail(FULL)
        rows = list(csv.DictReader(open(path)))
        self.assertEqual(list(rows[0].keys()), AUDIT_COLUMNS)
        self.assertEqual(len(rows), len(FULL.audit))


if __name__ == "__main__":
    unittest.main(verbosity=2)
