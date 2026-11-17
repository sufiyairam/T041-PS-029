"""
workflow.py  -  STEP 7 + 8: process commands.txt, track every claim's state,
apply the SLA clock and auto-escalation.   (BR-08, BR-09)

Claim states:   NOT_SUBMITTED -> PENDING_APPROVAL -> APPROVED
                                       |-> RETURNED -> (RESUBMIT) -> PENDING_APPROVAL
                                       |-> REJECTED

How time works: commands are processed strictly in FILE order. Before each command
we move the clock to that command's timestamp, and every claim whose SLA window ended
before then is escalated first (in date order).
"""
import csv
import os
from datetime import datetime, time

from approvals import chain_for_claim
from calendar_rules import breach_day

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
from paths import output_folder

# DECISION LOG #13: does ON_LEAVE stop an approver from acting?
# The README lists exactly three reasons to refuse an action (not the pending approver,
# is the claimant, is a peer) and leave is not one of them. In the sample data EMP-009 approves
# CLM-025 on 2026-10-01 while on leave. So leave does NOT block by default.
LEAVE_BLOCKS_APPROVAL = False


def parse_time(text):
    return datetime.strptime(text, TIME_FORMAT)


def show_time(moment):
    return moment.strftime(TIME_FORMAT)


class Engine:
    def __init__(self, claims, results, employees, cost_centres, holidays):
        self.claims = claims
        self.results = results
        self.employees = employees
        self.cost_centres = cost_centres
        self.holidays = holidays

        self.states = {}            # claim_id -> state dictionary
        self.audit = []             # rows for audit_trail.csv
        self.rejected = []          # commands we refused (rejected_commands.csv)
        self.leave = {}             # employee_id -> [(from_date, to_date), ...]
        self.report_requests = []   # PRINT_REPORT commands (used in Step 10)
        self.clock = None           # latest time we have processed

    # ------------------------------------------------------------------
    # main loop
    # ------------------------------------------------------------------
    def run(self, commands):
        """commands = [(line_no, [parts...]), ...] in file order."""
        for line_no, parts in commands:
            name = parts[0]
            if name == "ON_LEAVE":
                self.leave.setdefault(parts[1], []).append((parts[2], parts[3]))
                continue
            if name == "PRINT_REPORT":
                self.report_requests.append((line_no, parts[1], parts[2]))
                continue

            when = parse_time(parts[2] if name == "SUBMIT" or name == "RESUBMIT" else parts[3])
            self._advance_clock(when)

            if name == "SUBMIT":
                self._submit(line_no, parts[1], when)
            elif name == "RESUBMIT":
                self._resubmit(line_no, parts[1], when)
            elif name in ("APPROVE", "REJECT", "RETURN"):
                self._decide(line_no, name, parts[1], parts[2], when)
            else:
                self._refuse(line_no, name, parts[1] if len(parts) > 1 else "", "", when, "UNKNOWN_COMMAND")
        # time keeps running after the last command: pending claims can still breach
        # up to the last timestamp we saw. (_advance_clock was called for each command.)

    # ------------------------------------------------------------------
    # SLA clock
    # ------------------------------------------------------------------
    def _breach_moment(self, state):
        day = breach_day(state["step_started"].date(), self.holidays)
        return datetime.combine(day, time(0, 0, 0))

    def _advance_clock(self, until):
        if self.clock is not None and until <= self.clock:
            return                                   # file timestamps can go backwards: never rewind
        while True:
            due = [(self._breach_moment(s), cid) for cid, s in self.states.items()
                   if s["state"] == "PENDING_APPROVAL" and self._breach_moment(s) <= until]
            if not due:
                break
            moment, cid = min(due)
            self._breach(self.states[cid], moment)
        self.clock = until

    def _breach(self, state, moment):
        """The pending approver was too slow."""
        claim = self.claims[state["claim_id"]]
        current = state["pending"]

        # who is the approver's manager? (skip the claimant, who cannot approve their own claim)
        target = self.employees[current]["manager_id"]
        while target == claim["employee_id"]:
            target = self.employees[target]["manager_id"]

        if target != "NONE":
            state["pending"] = target                # escalate one level up
            state["step_started"] = moment           # the new approver gets a fresh SLA
            state["top_breaches"] = 0
            self._log(state, None, "ESCALATE", "SYSTEM", moment, state["step"] + 1)
            return

        # Already at the very top: nobody above to escalate to.
        state["top_breaches"] += 1
        state["step_started"] = moment
        if state["top_breaches"] == 1:
            self._log(state, None, "ESCALATE", "SYSTEM", moment, state["step"] + 1)
            return

        # Second breach in a row at the top: decide automatically.
        has_exception = any(self.results[(state["claim_id"], pos)]["decision"] == "EXCEPTION"
                            for pos in range(len(claim["lines"])))
        step_no = state["step"] + 1
        state["pending"] = None
        if has_exception:
            state["state"] = "RETURNED"              # exception lines go back to the employee
            self._log(state, None, "AUTO_RETURN", "SYSTEM", moment, step_no)
        else:
            state["state"] = "APPROVED"
            state["final_approval_at"] = moment
            self._log(state, None, "AUTO_APPROVE", "SYSTEM", moment, step_no)

    # ------------------------------------------------------------------
    # commands
    # ------------------------------------------------------------------
    def _submit(self, line_no, claim_id, when):
        if claim_id not in self.claims:
            return self._refuse(line_no, "SUBMIT", claim_id, "", when, "UNKNOWN_CLAIM")
        if claim_id in self.states:
            return self._refuse(line_no, "SUBMIT", claim_id, "", when, "ALREADY_SUBMITTED")
        claim = self.claims[claim_id]
        chain = [a for a, _ in chain_for_claim(claim, self.results, self.employees, self.cost_centres)]
        state = {"claim_id": claim_id, "chain": chain, "state": "PENDING_APPROVAL", "step": 0,
                 "pending": chain[0], "step_started": when, "top_breaches": 0,
                 "approved_by": set(), "final_approval_at": None, "submitted_at": when}
        self.states[claim_id] = state
        self._log(state, line_no, "SUBMIT", claim["employee_id"], when, 1)

    def _resubmit(self, line_no, claim_id, when):
        state = self.states.get(claim_id)
        claim = self.claims.get(claim_id)
        if state is None or state["state"] != "RETURNED":
            return self._refuse(line_no, "RESUBMIT", claim_id, "", when, "CLAIM_NOT_RETURNED")
        # chain restarts at step 1 with a fresh SLA
        state.update({"state": "PENDING_APPROVAL", "step": 0, "pending": state["chain"][0],
                      "step_started": when, "top_breaches": 0, "approved_by": set()})
        self._log(state, line_no, "RESUBMIT", claim["employee_id"], when, 1)

    def _decide(self, line_no, name, claim_id, actor, when):
        state = self.states.get(claim_id)
        if state is None:
            return self._refuse(line_no, name, claim_id, actor, when, "CLAIM_NOT_SUBMITTED")
        reason = self._why_invalid(state, actor, when)
        if reason:
            return self._refuse(line_no, name, claim_id, actor, when, reason)

        step_no = state["step"] + 1
        if name == "REJECT":
            state["state"], state["pending"] = "REJECTED", None
        elif name == "RETURN":
            state["state"], state["pending"] = "RETURNED", None       # SLA clock stops
        else:                                                         # APPROVE
            state["approved_by"].add(actor)
            # DECISION LOG #14: every step needs its OWN approval, even if the same person
            # is pending twice (CLM-035: EMP-004 approves once as the escalated approver
            # and again as the cost-centre head, exactly as commands.txt shows).
            state["step"] += 1
            if state["step"] >= len(state["chain"]):
                state["state"], state["pending"] = "APPROVED", None
                state["final_approval_at"] = when
            else:
                state["pending"] = state["chain"][state["step"]]
                state["step_started"] = when                          # next approver: fresh SLA
                state["top_breaches"] = 0
        self._log(state, line_no, name, actor, when, step_no)

    def _why_invalid(self, state, actor, when):
        """Return the reason this action must be refused, or None if it is fine."""
        claim = self.claims[state["claim_id"]]
        if state["state"] != "PENDING_APPROVAL":
            return "CLAIM_NOT_PENDING (" + state["state"] + ")"
        if actor == claim["employee_id"]:
            return "SELF_APPROVAL"
        if LEAVE_BLOCKS_APPROVAL and self._on_leave(actor, when):
            return "APPROVER_ON_LEAVE"
        if actor != state["pending"]:
            same_grade = (actor in self.employees and
                          self.employees[actor]["grade"] == self.employees[state["pending"]]["grade"])
            return "PEER_NOT_PENDING_APPROVER" if same_grade else "NOT_PENDING_APPROVER"
        return None

    def _on_leave(self, employee_id, when):
        day = when.date().isoformat()
        return any(start <= day <= end for start, end in self.leave.get(employee_id, []))

    # ------------------------------------------------------------------
    # logging and output files
    # ------------------------------------------------------------------
    def _log(self, state, line_no, event, actor, when, step_no):
        self.audit.append({
            "claim_id": state["claim_id"],
            "line_no_in_commands": "" if line_no is None else line_no,
            "event": event, "actor": actor, "timestamp": show_time(when),
            "step_no": step_no, "pending_approver": state["pending"] or "",
            "state_after": state["state"], "chain": ";".join(state["chain"]),
        })

    def _refuse(self, line_no, name, claim_id, actor, when, reason):
        self.rejected.append({"line_no_in_commands": line_no, "command": name, "claim_id": claim_id,
                              "actor": actor, "timestamp": show_time(when), "reason": reason})


AUDIT_COLUMNS = ["claim_id", "line_no_in_commands", "event", "actor", "timestamp", "step_no",
                 "pending_approver", "state_after", "chain"]
REFUSED_COLUMNS = ["line_no_in_commands", "command", "claim_id", "actor", "timestamp", "reason"]


def write_audit_trail(engine, path=None):
    """One row per claim per event. Rows are grouped by claim, in the order they happened."""
    os.makedirs(output_folder(), exist_ok=True)
    path = path or os.path.join(output_folder(), "audit_trail.csv")
    rows = sorted(enumerate(engine.audit), key=lambda pair: (pair[1]["claim_id"], pair[0]))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=AUDIT_COLUMNS, lineterminator="\n")
        w.writeheader()
        for _, row in rows:
            w.writerow(row)
    return path


def write_refused_commands(engine, path=None):
    os.makedirs(output_folder(), exist_ok=True)
    path = path or os.path.join(output_folder(), "rejected_commands.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REFUSED_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(engine.rejected)
    return path


def run_workflow():
    """Load everything, validate the lines, and process commands.txt. Returns the Engine."""
    from loader import load_employees, load_cost_centres, load_holidays, load_commands_with_lines
    from pipeline import validate_all
    claims, results = validate_all()
    engine = Engine(claims, results, load_employees(), load_cost_centres(), load_holidays())
    engine.run(load_commands_with_lines())
    return engine
