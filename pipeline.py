"""
pipeline.py  -  STEP 5: run EVERY line rule on EVERY claim line, then write
output/line_decisions.csv

Order of rules for each line:
   1. convert money to rupees           (BR-10)
   2. timeliness                        (BR-05)
   3. hotel / per diem / travel / meals (BR-01, BR-02, BR-03, BR-07)
   4. receipts (whole claim at once)    (BR-04)
   5. duplicates (all claims at once)   (BR-06)
   6. taxable amount
"""
import csv
import os
from decimal import Decimal

from loader import (load_claims, load_employees, load_fx_rates, load_city_tiers,
                    load_hotel_caps, load_per_diem, load_travel_entitlements)
from rules import (convert_to_inr, new_result, check_timeliness, check_hotel,
                   check_per_diem, check_travel, check_team_meal, check_receipts,
                   check_duplicates, lines_for_meal_check)

from paths import output_folder

# DECISION LOG #6: only the part of a HOTEL exception ABOVE THE CAP is taxable.
#   Other exceptions (late claim, travel class with no entitled fare) have no
#   cap amount to compare with, so nothing is taxable there.
#   The taxable_amount in line_decisions.csv is what WOULD be taxable if the
#   exception is approved. Settlement (Step 8) counts it only for approved claims.


def validate_all():
    """Run all line rules. Returns (claims, results_by_key).
    results_by_key[(claim_id, position_in_claim)] = result for that line."""
    claims = load_claims()
    employees = load_employees()
    fx = load_fx_rates()
    tiers = load_city_tiers()
    hotel_caps = load_hotel_caps()
    per_diem = load_per_diem()
    travel = load_travel_entitlements()

    results_by_key = {}
    for claim in claims.values():
        grade = employees[claim["employee_id"]]["grade"]
        claim_results = []
        for pos, line in enumerate(claim["lines"]):
            inr, rate = convert_to_inr(line, fx)
            result = new_result(line, inr, rate)

            check_timeliness(result, line, claim)
            check_hotel(result, line, grade, tiers, hotel_caps)
            check_per_diem(result, line, tiers, per_diem, lines_for_meal_check(claims, claim, line))
            check_travel(result, line, grade, travel)
            check_team_meal(result, line, grade, employees)

            claim_results.append(result)
            results_by_key[(claim["claim_id"], pos)] = result

        check_receipts(claim_results, claim["lines"])      # needs the whole claim

    check_duplicates(claims, results_by_key)               # needs all claims

    for result in results_by_key.values():                 # taxable amount
        if result["decision"] == "EXCEPTION":
            result["taxable_amount"] = result.get("cap_excess", Decimal("0.00"))
    return claims, results_by_key


def write_line_decisions(claims, results_by_key, path=None):
    os.makedirs(output_folder(), exist_ok=True)
    path = path or os.path.join(output_folder(), "line_decisions.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["claim_id", "line_no", "category", "amount_inr", "rate_used",
                    "decision", "allowed_amount", "rule_ids", "flags", "taxable_amount"])
        for claim in claims.values():
            for pos in range(len(claim["lines"])):
                r = results_by_key[(claim["claim_id"], pos)]
                w.writerow([r["claim_id"], r["line_no"], r["category"],
                            f'{r["amount_inr"]:.2f}', f'{r["rate_used"]:.2f}',
                            r["decision"], f'{r["allowed_amount"]:.2f}',
                            ";".join(sorted(r["rule_ids"])), ";".join(r["flags"]),
                            f'{r["taxable_amount"]:.2f}'])
    return path
