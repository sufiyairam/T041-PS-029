"""
approvals.py  -  STEP 6: build the approval chain for a claim  (BR-08)

The chain is the ORDERED list of people who must approve, one after another.

  Total payable   Who approves
  --------------  ------------------------------------------------
  (total = everything the employee claimed, in rupees)
  up to 10,000    the claimant's manager
  up to 50,000    manager + cost-centre head
  above 50,000    manager + cost-centre head + finance controller

  Extras (added at the end, only if nobody in the chain already qualifies):
  - any EXCEPTION line               -> someone of grade E5
  - team meal with > 10 attendees    -> someone of grade E4 or higher

  Cleaning: nobody approves their own claim, and the same person is never
  listed twice (e.g. when the manager IS the cost-centre head).
"""
from decimal import Decimal

from rules import grade_number

LIMIT_MANAGER_ONLY = Decimal("10000")        # <= 10,000 -> manager only
LIMIT_NO_CONTROLLER = Decimal("50000")       # <= 50,000 -> no finance controller

# DECISION LOG #10: which total decides the chain?
#   "CLAIMED" -> everything the employee wrote on the claim (our choice)
#   "ALLOWED" -> only the money we are willing to pay (rejected lines removed, caps applied)
# Why CLAIMED: CLM-022 claims Rs 54,200 (payable Rs 44,400) and commands.txt shows the
# finance controller EMP-002 approving it, so the sample data uses the claimed total.
CHAIN_TOTAL_BASIS = "CLAIMED"


def find_finance_controller(employees):
    """The employee whose role is FINANCE_CONTROLLER (EMP-002 in the sample data)."""
    for emp_id, e in employees.items():
        if e["role"] == "FINANCE_CONTROLLER":
            return emp_id
    return None


def first_with_grade_up_the_line(claimant_id, minimum_grade, employees):
    """Walk up the manager line of the claimant and return the first person whose
    grade is at least `minimum_grade` (3 means E3 or higher). None if nobody."""
    current = employees[claimant_id]["manager_id"]
    while current != "NONE" and current in employees:
        if grade_number(employees[current]["grade"]) >= minimum_grade:
            return current
        current = employees[current]["manager_id"]
    return None


def build_chain(claimant_id, total, has_exception, needs_e4, employees, cost_centres):
    """Return the chain as a list of (approver_id, why) in the order they must approve.

    claimant_id   : employee who made the claim
    total         : Decimal, total of the claim (see CHAIN_TOTAL_BASIS)
    has_exception : True if any line is an EXCEPTION
    needs_e4      : True if a line has the NEEDS_E4_APPROVAL flag
    """
    claimant = employees[claimant_id]
    steps = []                                   # list of (approver_id, why)

    # 1. the manager always approves
    steps.append((claimant["manager_id"], "MANAGER"))

    # 2. cost-centre head for claims above 10,000
    if total > LIMIT_MANAGER_ONLY:
        head = cost_centres[claimant["cost_centre"]]["head_employee_id"]
        steps.append((head, "CC_HEAD"))

    # 3. finance controller for claims above 50,000
    if total > LIMIT_NO_CONTROLLER:
        steps.append((find_finance_controller(employees), "FINANCE_CONTROLLER"))

    # Clean up: remove 'NONE', the claimant themself, and repeated people
    chain, seen = [], set()
    for approver, why in steps:
        if approver in (None, "NONE", claimant_id) or approver in seen:
            continue
        chain.append((approver, why))
        seen.add(approver)

    # 4. extras. Skipped if someone in the chain already has a high enough grade.
    def chain_has_grade(minimum):
        return any(grade_number(employees[a]["grade"]) >= minimum for a, _ in chain)

    if needs_e4 and not chain_has_grade(4):
        extra = first_with_grade_up_the_line(claimant_id, 4, employees)
        if extra and extra not in seen:
            chain.append((extra, "E4_FOR_LARGE_GROUP")); seen.add(extra)

    if has_exception and not chain_has_grade(5):
        extra = first_with_grade_up_the_line(claimant_id, 5, employees)
        if extra and extra not in seen:
            chain.append((extra, "E5_FOR_EXCEPTION")); seen.add(extra)

    # Safety net: a chain must never be empty
    if not chain:
        fallback = find_finance_controller(employees)
        if fallback == claimant_id:
            fallback = first_with_grade_up_the_line(claimant_id, 5, employees) or fallback
        chain.append((fallback, "FINANCE_CONTROLLER"))
    return chain


def chain_for_claim(claim, results_by_key, employees, cost_centres):
    """Build the chain for a real claim, using the line decisions from pipeline.py."""
    results = [results_by_key[(claim["claim_id"], pos)] for pos in range(len(claim["lines"]))]
    key = "allowed_amount" if CHAIN_TOTAL_BASIS == "ALLOWED" else "amount_inr"
    total = sum((r[key] for r in results), Decimal("0.00"))
    has_exception = any(r["decision"] == "EXCEPTION" for r in results)
    needs_e4 = any("NEEDS_E4_APPROVAL" in r["flags"] for r in results)
    return build_chain(claim["employee_id"], total, has_exception, needs_e4, employees, cost_centres)
