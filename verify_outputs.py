"""
verify_outputs.py  -  an independent self-check of the 4 output files.

It does NOT use our rule code. It only reads the CSV files in output/ and checks them
against the brief:   python verify_outputs.py
Run `python main.py` first.
"""
import csv
import os
import sys
from datetime import date, timedelta
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from paths import data_folder, output_folder
OUT = output_folder()
DATA = data_folder()

checks = []


def check(name, ok):
    checks.append((name, bool(ok)))


def rows(folder, name):
    with open(os.path.join(folder, name), newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


lines = rows(OUT, "line_decisions.csv")
audit = rows(OUT, "audit_trail.csv")
settle = {r["claim_id"]: r for r in rows(OUT, "claim_settlement.csv")}
report = rows(OUT, "cost_centre_report.csv")
holidays = {r["date"] for r in rows(DATA, "holidays.csv")}
D = Decimal


def line(claim, category, nth=0, amount=None):
    found = [r for r in lines if r["claim_id"] == claim and r["category"] == category
             and (amount is None or D(r["amount_inr"]) == D(amount))]
    return found[nth] if len(found) > nth else None


# ---------------- the 8 edge cases named in the brief ----------------
r = line("CLM-015", "HOTEL")
check("EDGE 1  hotel at exactly 150% of cap -> EXCEPTION (not rejected), BR-01",
      r and r["decision"] == "EXCEPTION" and "BR-01" in r["rule_ids"])

a, b = line("CLM-013", "TAXI", 0), line("CLM-013", "TAXI", 1)
check("EDGE 2  line on day 60 ALLOWED, line on day 61 EXCEPTION (BR-05)",
      a and b and a["decision"] == "ALLOWED" and b["decision"] == "EXCEPTION" and "BR-05" in b["rule_ids"])

pd, meal = line("CLM-021", "PER_DIEM", amount="1000"), line("CLM-021", "MEAL")
check("EDGE 3  per diem next to a Rs 0 itemised meal -> per diem still ALLOWED",
      pd and meal and pd["decision"] == "ALLOWED" and D(meal["amount_inr"]) == 0)

fl = [x for x in lines if x["claim_id"] == "CLM-022" and x["category"] == "FLIGHT"]
check("EDGE 4  E4 business flight of exactly 4.00 h -> EXCEPTION (BR-03)",
      any(x["decision"] == "EXCEPTION" and "BR-03" in x["rule_ids"] for x in fl))

t = [x for x in lines if x["claim_id"] == "CLM-027" and x["category"] == "TAXI"]
fourth = next((x for x in t if D(x["amount_inr"]) == D("500")), None)
check("EDGE 5  4th missing-receipt line of Rs 500.00 -> REJECTED (BR-04)",
      fourth and fourth["decision"] == "REJECTED" and "BR-04" in fourth["rule_ids"])

esc = [x for x in audit if x["claim_id"] == "CLM-023" and x["event"] == "ESCALATE"]
check("EDGE 6  CLM-023 approver on leave: SLA breach moves past the 2 Oct holiday to Mon 5 Oct",
      esc and esc[0]["timestamp"].startswith("2026-10-05") and esc[0]["pending_approver"] == "EMP-004")

h = line("CLM-018", "HOTEL")
tx = [x for x in lines if x["claim_id"] == "CLM-018" and x["category"] == "TAXI"]
check("EDGE 7  card rate exactly 2.0% from policy IS used (85.17); 2.16% is NOT (83.50)",
      h and D(h["rate_used"]) == D("85.17") and tx and D(tx[0]["rate_used"]) == D("83.50"))

s = settle["CLM-029"]
check("EDGE 8  advance (40,000) bigger than approved claim -> payout 0, rest recovered",
      D(s["net_payout"]) == 0 and D(s["advance_recovered_from_salary"]) == D(s["advance_amount"]) - D(s["approved_total_inr"]))

# ---------------- line_decisions.csv ----------------
check("LINES   one row per claim line (280)", len(lines) == 280)
check("LINES   decision is one of the 4 allowed words", all(r["decision"] in ("ALLOWED", "CAPPED", "EXCEPTION", "REJECTED") for r in lines))
check("LINES   allowed_amount never above amount_inr", all(D(r["allowed_amount"]) <= D(r["amount_inr"]) for r in lines))
check("LINES   REJECTED lines allow 0.00", all(D(r["allowed_amount"]) == 0 for r in lines if r["decision"] == "REJECTED"))
check("LINES   CAPPED lines allow less than claimed", all(D(r["allowed_amount"]) < D(r["amount_inr"]) for r in lines if r["decision"] == "CAPPED"))
check("LINES   every non-ALLOWED line names a rule id", all(r["rule_ids"] for r in lines if r["decision"] != "ALLOWED"))
check("LINES   taxable amount only on EXCEPTION lines", all(D(r["taxable_amount"]) == 0 for r in lines if r["decision"] != "EXCEPTION"))

# ---------------- settlement ----------------
def add_working_days(d, n):
    while n:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in holidays:
            n -= 1
    return d

ok_math = ok_sum = ok_pay = ok_state = True
last_state = {}
for r in audit:
    last_state[r["claim_id"]] = r["state_after"]
for cid, s in settle.items():
    approved, adv, pay, rec = D(s["approved_total_inr"]), D(s["advance_amount"]), D(s["net_payout"]), D(s["advance_recovered_from_salary"])
    if s["final_state"] == "APPROVED":
        ok_math &= (pay == max(D(0), approved - adv)) and (rec == max(D(0), adv - approved))
        allowed = sum(D(x["allowed_amount"]) for x in lines if x["claim_id"] == cid)
        ok_sum &= (allowed == approved)
        d = date.fromisoformat(s["final_approval_at"][:10])
        ok_pay &= (s["pay_by_date"] == add_working_days(d, 5).isoformat())
    else:
        ok_math &= (pay == 0 and approved == 0)
    ok_state &= (s["final_state"] == last_state[cid])
check("SETTLE  payout = max(0, approved - advance); recovered = max(0, advance - approved)", ok_math)
check("SETTLE  approved total = sum of allowed line amounts (approved claims)", ok_sum)
check("SETTLE  pay_by_date = 5 working days after final approval", ok_pay)
check("SETTLE  final_state equals the last state in the audit trail", ok_state)
check("SETTLE  one row per claim (40)", len(settle) == 40)

# ---------------- audit trail ----------------
by_claim = {}
for r in audit:
    by_claim.setdefault(r["claim_id"], []).append(r)
ok_first = ok_actor = ok_chain = ok_self = True
for cid, evs in by_claim.items():
    ok_first &= evs[0]["event"] == "SUBMIT"
    chain = evs[0]["chain"].split(";")
    ok_chain &= all(e["chain"] == evs[0]["chain"] for e in evs)
    prev_pending = evs[0]["pending_approver"]
    for e in evs[1:]:
        if e["event"] in ("APPROVE", "REJECT", "RETURN"):
            ok_actor &= (e["actor"] == prev_pending)          # only the pending approver may act
            ok_self &= (e["actor"] != settle[cid]["employee_id"])
        prev_pending = e["pending_approver"] if e["pending_approver"] else prev_pending
check("AUDIT   every claim starts with SUBMIT", ok_first)
check("AUDIT   every APPROVE/REJECT/RETURN was done by the approver that was pending", ok_actor)
check("AUDIT   nobody acted on their own claim", ok_self)
check("AUDIT   chain never changes during a claim", ok_chain)
check("AUDIT   approved claims have one APPROVE per chain step (or an AUTO_APPROVE)",
      all(sum(e["event"] == "APPROVE" for e in evs[max(i for i, e in enumerate(evs) if e["event"] in ("SUBMIT", "RESUBMIT")):]) >= len(evs[0]["chain"].split(";"))
          or any(e["event"] == "AUTO_APPROVE" for e in evs)
          for cid, evs in by_claim.items() if settle[cid]["final_state"] == "APPROVED"))

# ---------------- report ----------------
sub_month = {cid: evs[0]["timestamp"][:7] for cid, evs in by_claim.items()}
months = {r["month"] for r in report}
check("REPORT  claims_count adds up to the claims submitted in those months",
      sum(int(r["claims_count"]) for r in report) == sum(1 for m in sub_month.values() if m in months))

# ---------------- print ----------------
width = max(len(n) for n, _ in checks)
for name, ok in checks:
    print(("PASS  " if ok else "FAIL  ") + name)
failed = [n for n, ok in checks if not ok]
print(f"\n{len(checks) - len(failed)} of {len(checks)} checks passed")
sys.exit(1 if failed else 0)
