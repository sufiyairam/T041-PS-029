"""Print the approval chain of every claim:   python show_chains.py"""
from loader import load_employees, load_cost_centres
from pipeline import validate_all
from approvals import chain_for_claim

claims, results = validate_all()
employees, cost_centres = load_employees(), load_cost_centres()

print(f'{"claim":8} {"claimant":8} chain')
for cid, claim in claims.items():
    chain = chain_for_claim(claim, results, employees, cost_centres)
    print(f'{cid:8} {claim["employee_id"]:8} ' + "  ->  ".join(f"{a} ({why})" for a, why in chain))
