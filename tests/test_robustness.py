import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)

import csv
import shutil
import subprocess
import tempfile
import unittest
from decimal import Decimal

from rules import find_policy_rate, new_result, check_hotel, check_per_diem, convert_to_inr
from loader import load_claims, load_city_tiers, load_hotel_caps, load_per_diem, load_fx_rates

MAIN = os.path.join(ROOT, "main.py")


def run_main_on(data_dir, from_folder):
    out = tempfile.mkdtemp()
    done = subprocess.run([sys.executable, MAIN, data_dir, out], cwd=from_folder,
                          capture_output=True, text=True)
    return done, out


def copy_data():
    folder = tempfile.mkdtemp()
    data = os.path.join(folder, "data")
    shutil.copytree(os.path.join(ROOT, "data"), data)
    return data


def rewrite_csv(path, change):
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8-sig")))
    change(rows)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:      # utf-8-sig = Excel style (BOM)
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)


def payout_of(out):
    rows = list(csv.DictReader(open(os.path.join(out, "claim_settlement.csv"))))
    return sum(Decimal(r["net_payout"]) for r in rows)


class TestRobustness(unittest.TestCase):

    def test_runs_from_any_folder_with_custom_data_and_output_folders(self):
        done, out = run_main_on(os.path.join(ROOT, "data"), tempfile.gettempdir())
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(payout_of(out), Decimal("559879.00"))
        for name in ("line_decisions", "audit_trail", "claim_settlement", "cost_centre_report"):
            self.assertTrue(os.path.exists(os.path.join(out, name + ".csv")))

    def test_excel_files_with_bom_and_windows_line_endings(self):
        data = copy_data()
        for name in os.listdir(data):
            if name.endswith(".csv"):
                rewrite_csv(os.path.join(data, name), lambda rows: None)
        done, out = run_main_on(data, tempfile.gettempdir())
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(payout_of(out), Decimal("559879.00"))

    def test_blank_cells_mean_not_applicable(self):
        data = copy_data()
        def blank(rows):
            for r in rows:
                for k in r:
                    if r[k] == "NA":
                        r[k] = ""
        rewrite_csv(os.path.join(data, "claim_lines.csv"), blank)
        done, out = run_main_on(data, tempfile.gettempdir())
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(payout_of(out), Decimal("559879.00"))

    def test_missing_data_folder_gives_a_friendly_message(self):
        done, _ = run_main_on(os.path.join(tempfile.gettempdir(), "no_such_folder_xyz"), tempfile.gettempdir())
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("Could not find an input file", done.stderr)
        self.assertNotIn("Traceback", done.stderr)

    def test_empty_command_file_runs(self):
        data = copy_data()
        open(os.path.join(data, "commands.txt"), "w").close()
        done, out = run_main_on(data, tempfile.gettempdir())
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(payout_of(out), Decimal("0"))

    def test_nonsense_commands_are_refused_not_crashing(self):
        data = copy_data()
        with open(os.path.join(data, "commands.txt"), "a") as f:
            f.write("APPROVE|CLM-999|EMP-001|2026-10-27 10:00:00|\n"
                    "SUBMIT|CLM-001|2026-10-27 10:00:00\n"
                    "RESUBMIT|CLM-001|2026-10-27 10:00:00|x\n"
                    "FOOBAR|CLM-001|EMP-001|2026-10-27 10:00:00\n")
        done, out = run_main_on(data, tempfile.gettempdir())
        self.assertEqual(done.returncode, 0, done.stderr)
        refused = list(csv.DictReader(open(os.path.join(out, "rejected_commands.csv"))))
        self.assertEqual(len(refused), 3 + 4)

    def test_missing_fx_date_uses_latest_earlier_rate(self):
        rates = {("USD", "2026-09-08"): 83.0, ("USD", "2026-09-09"): 83.4}
        self.assertEqual(find_policy_rate(rates, "USD", "2026-09-10"), 83.4)
        self.assertEqual(find_policy_rate(rates, "USD", "2026-09-09"), 83.4)
        with self.assertRaises(ValueError):
            find_policy_rate(rates, "USD", "2026-12-01")

    def test_unknown_city_becomes_exception_not_a_crash(self):
        claims = load_claims(); fx = load_fx_rates()
        hotel = dict(next(l for l in claims["CLM-003"]["lines"] if l["category"] == "HOTEL")); hotel["city"] = "Atlantis"
        inr, rate = convert_to_inr(hotel, fx)
        r = new_result(hotel, inr, rate)
        check_hotel(r, hotel, "E1", load_city_tiers(), load_hotel_caps())
        self.assertEqual(r["decision"], "EXCEPTION")
        self.assertIn("UNKNOWN_CITY_OR_GRADE", r["flags"])

        diem = dict(next(l for l in claims["CLM-003"]["lines"] if l["category"] == "PER_DIEM")); diem["city"] = "Atlantis"
        inr, rate = convert_to_inr(diem, fx)
        r = new_result(diem, inr, rate)
        check_per_diem(r, diem, load_city_tiers(), load_per_diem(), [diem])
        self.assertEqual(r["decision"], "EXCEPTION")


if __name__ == "__main__":
    unittest.main(verbosity=2)
