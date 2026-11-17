"""
main.py  -  run with:   python main.py
  Step 5   validates every claim line            -> output/line_decisions.csv
  Step 7+8 processes commands.txt (SLA, escalation) -> output/audit_trail.csv
                                                   -> output/rejected_commands.csv
  Step 9   settlement (advance, tax, payout)       -> output/claim_settlement.csv
  Step 10  monthly cost-centre report              -> output/cost_centre_report.csv
"""
import os
import sys
from collections import Counter

# Optional:  python main.py  <data_folder>  <output_folder>
if len(sys.argv) > 1:
    os.environ["EXPENSE_DATA_DIR"] = os.path.abspath(sys.argv[1])
if len(sys.argv) > 2:
    os.environ["EXPENSE_OUTPUT_DIR"] = os.path.abspath(sys.argv[2])

from pipeline import write_line_decisions
from workflow import run_workflow, write_audit_trail, write_refused_commands
from settlement import write_claim_settlement, build_settlement_rows
from reports import write_cost_centre_report

try:
    engine = run_workflow()
except FileNotFoundError as problem:
    sys.exit(f"Could not find an input file: {problem.filename}\n"
             "Put the CSV files and commands.txt in the data folder, or run:  python main.py <data_folder>")
except (KeyError, ValueError) as problem:
    sys.exit(f"The input data has a problem: {problem!r}. Check column names and values in the data folder.")
line_path = write_line_decisions(engine.claims, engine.results)
audit_path = write_audit_trail(engine)
refused_path = write_refused_commands(engine)
settlement_path = write_claim_settlement(engine)
report_path = write_cost_centre_report(engine)

print("Claims checked      :", len(engine.claims))
print("Lines checked       :", len(engine.results))
print("Line decisions      :", dict(Counter(r["decision"] for r in engine.results.values())))
print("Claim states        :", dict(Counter(s["state"] for s in engine.states.values())))
print("Audit events        :", dict(Counter(r["event"] for r in engine.audit)))
print("Commands refused    :", len(engine.rejected))
print("Written to          :", line_path)
print("                      ", audit_path)
print("                      ", refused_path)
print("                      ", settlement_path)
print("                      ", report_path)
rows = build_settlement_rows(engine)
print("Total payout (Rs)  :", sum(float(r["net_payout"]) for r in rows))
print("Recovered from salary (Rs):", sum(float(r["advance_recovered_from_salary"]) for r in rows))
