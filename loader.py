"""
loader.py  -  STEP 1: read all the input files into Python.

Idea: every CSV file becomes a LIST of ROWS.
Each row is a DICTIONARY, like {"employee_id": "EMP-001", "grade": "E5", ...}
So you can write row["grade"] to get a value.
"""
import csv
import os

from paths import data_folder


def read_csv(filename):
    """Open a CSV file and return a list of rows (dictionaries)."""
    path = os.path.join(data_folder(), filename)
    # utf-8-sig: files saved by Excel as "CSV UTF-8" start with an invisible marker (BOM)
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = []
        for row in csv.DictReader(f):
            # remove stray spaces around names and values; a missing cell becomes ""
            rows.append({(k or "").strip(): (v or "").strip() for k, v in row.items()})
        return rows


def load_employees():
    """Return {"EMP-001": {...row...}, ...} so we can find a person by id."""
    return {row["employee_id"]: row for row in read_csv("employees.csv")}


def load_cost_centres():
    """Return {"CC-100": {...}, ...}"""
    return {row["cost_centre"]: row for row in read_csv("cost_centres.csv")}


def load_city_tiers():
    """Return {"Mumbai": {...tier 1...}, ...}"""
    return {row["city"]: row for row in read_csv("city_tiers.csv")}


def load_hotel_caps():
    """Return {("E2", "1"): 4500.0, ...}  (grade, tier) -> cap per night."""
    return {(r["grade"], r["tier"]): float(r["cap_per_night"])
            for r in read_csv("hotel_caps.csv")}


def load_per_diem():
    """Return {"TIER1": 1000.0, "INTL": 50.0, ...}"""
    return {r["scope"]: float(r["rate"]) for r in read_csv("per_diem.csv")}


def load_travel_entitlements():
    """Return {"E4": {...}, ...}"""
    return {r["grade"]: r for r in read_csv("travel_entitlements.csv")}


def load_holidays():
    """Return a set of date strings like {"2026-10-02", ...}"""
    return {r["date"] for r in read_csv("holidays.csv")}


def load_fx_rates():
    """Return {("USD", "2026-09-10"): 83.5, ...}  (currency, date) -> rate."""
    return {(r["currency"], r["date"]): float(r["rate_inr"])
            for r in read_csv("fx_rates.csv")}


def load_claims():
    """Return {"CLM-001": {...claim row..., "lines": [...]}, ...}
    Each claim gets its own list of lines attached."""
    claims = {r["claim_id"]: r for r in read_csv("claims.csv")}
    for claim in claims.values():
        claim["lines"] = []
        if claim.get("advance_amount", "") in ("", "NA"):
            claim["advance_amount"] = "0.00"                 # no advance
    for line in read_csv("claim_lines.csv"):
        for key, value in line.items():
            if value == "":
                line[key] = "NA"                             # a blank cell means "not applicable"
        claims[line["claim_id"]]["lines"].append(line)
    return claims


def load_commands():
    """Return a list of commands in file order.
    Example: ["APPROVE", "CLM-001", "EMP-006", "2026-08-26 13:40:00", ""]"""
    commands = []
    with open(os.path.join(data_folder(), "commands.txt"), encoding="utf-8-sig") as f:
        for text in f:
            text = text.strip()
            if text == "" or text.startswith("#"):
                continue                      # skip blank lines and comments
            commands.append([p.strip() for p in text.split("|")])  # split on the | symbol
    return commands


def load_commands_with_lines():
    """Like load_commands(), but each command comes with its PHYSICAL line number
    in commands.txt (comment lines count). Returns [(line_no, [parts...]), ...]"""
    commands = []
    with open(os.path.join(data_folder(), "commands.txt"), encoding="utf-8-sig") as f:
        for line_no, text in enumerate(f, start=1):
            text = text.strip()
            if text == "" or text.startswith("#"):
                continue
            commands.append((line_no, [p.strip() for p in text.split("|")]))
    return commands
