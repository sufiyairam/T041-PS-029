# Decision Log - Team T041 (PS-029)

Where the brief or data was unclear, we made a choice. Each one is a single setting in `rules.py`.

| # | Question | Our decision | Setting in rules.py |
|---|----------|--------------|---------------------|
| 1 | hotel_caps.csv has no cap for international (INTL) cities | No hotel cap applies abroad | `INTL_HOTEL_RULE = "NO_CAP"` |
| 2 | Does a Rs 0 meal line block a per diem on the same day? | No. Nothing was spent, so it is not a real claim | `ZERO_MEAL_BLOCKS_PER_DIEM = False` |
| 3 | What counts as "same day" for per diem vs meals? | Lines in the SAME claim. The brief says "same day" without naming claims, but the README only plants the clash inside one claim, and the duplicate rule is the one that says "across any claim". Impact if this is wrong: see #33 (7 lines, Rs 6,000) | `PER_DIEM_MEAL_SCOPE = "CLAIM"` |
| 4 | How do we detect alcohol? | Category ALCOHOL, or words like drink/alcohol/wine/beer in the description | `ALCOHOL_WORDS` |
| 5 | Duplicate rule: apply literally? | Yes. The later line is rejected, even for repeated taxis or per diems | `DUPLICATE_TOLERANCE = 1` |
| 6 | Per diem lines have no receipt | Per diem is exempt from the receipt rule | `check_receipts()` |
| 7 | Team meals count as itemised meals for the per diem clash | Yes (MEAL and TEAM_MEAL) | `ITEMISED_MEAL_CATEGORIES` |
| 8 | line_no is not unique in the data (CLM-015, 018, 021, 022) | We identify lines by their position in the claim | `check_duplicates()` |
| 9 | Which part of an exception is taxable? | Only the part ABOVE THE CAP of a hotel or per diem exception (see #32). Late claims and travel-class exceptions have no cap amount, so nothing is taxable there. Counted at settlement only for approved claims | `rules.compute_taxable_amount()` |
| 10 | Which total decides the approval chain? | The CLAIMED total (all lines). CLM-022 claims 54,200 (payable 44,400) and commands.txt shows the finance controller approving | `CHAIN_TOTAL_BASIS = "CLAIMED"` |
| 11 | Exception needs E5 and big group needs E4: add a person even if the chain already has one? | No. If someone in the chain already has the grade (e.g. the finance controller is E5, a CC head is E4) nothing is added. Otherwise the first person of that grade up the claimant's manager line is added | `build_chain()` |
| 12 | Claimant is also in the chain (e.g. claimant is the CC head) | They are removed from their own chain; the same person is never listed twice | `build_chain()` |
| 13 | Does ON_LEAVE stop an approver acting? | No. The README lists only 3 reasons to refuse an action, and the sample data has EMP-009 approving CLM-025 while on leave. Leave only explains why an SLA is missed | `LEAVE_BLOCKS_APPROVAL = False` |
| 14 | Same person pending twice (escalated approver + their own step) | Each step needs its own approval (CLM-035 shows EMP-004 approving twice) | `workflow._decide()` |
| 15 | When is an escalation recorded, and at what time? | On the breach day (first working day after the deadline), at 00:00:00. Row has actor SYSTEM and no command line number | `workflow._breach()` |
| 16 | What are "two consecutive escalations at the top"? | The top approver (no manager above, EMP-001) misses the SLA twice in a row. 1st = ESCALATE (stays with the top, fresh SLA), 2nd = AUTO_APPROVE if no EXCEPTION line, otherwise AUTO_RETURN (claim goes back to the employee). Sample: CLM-013 | `workflow._breach()` |
| 17 | Refused commands (self/peer/not pending/claim not pending) | Not written to audit_trail.csv (they do not affect a claim) but listed in output/rejected_commands.csv | `write_refused_commands()` |
| 18 | audit_trail.csv row order | Grouped by claim_id, then in the order events happened | `write_audit_trail()` |
| 19 | What happens to the advance of a REJECTED claim? | The whole advance is recovered from salary (nothing was spent legitimately). RETURNED/open claims are not settled yet, so nothing is recovered | `settlement.settle()` |
| 20 | Is the taxable amount deducted from the payout? | No. Taxable perquisite is only REPORTED per claim; payroll deducts the tax. net_payout = approved total - advance (never below 0) | `settlement.settle()` |
| 21 | Final state of an approved claim | APPROVED (payment is due by pay_by_date). There is no payment command, so we never set PAID | `build_settlement_rows()` |
| 22 | How is pay_by_date counted? | 5 working days AFTER the approval date (next working day = day 1), skipping weekends and holidays | `PAY_WITHIN_WORKING_DAYS` |
| 23 | Taxable and approved totals for claims that are not APPROVED | 0.00, even for CLM-013 (auto-returned: exception lines go back, the claim is not part-paid) | `build_settlement_rows()` |
| 24 | Domestic per diem above Rs 1,000 a day is taxable | Implemented as its own clause in `compute_taxable_amount()`: for a domestic per diem line that is not rejected, paid amount minus 1,000 is taxable. With the shipped table (tier 1 = 1,000, tier 2/3 = 750) the cap already keeps normal claims under it; the clause matters for approved exceptions (see #32) and if per_diem.csv ever pays more than 1,000 | `rules.compute_taxable_amount()` |
| 25 | Which month does a claim belong to in the report? | The month of its first SUBMIT (every claim has one, even rejected or returned ones). RESUBMIT does not move it. So CLM-001 to CLM-005 (submitted in August) are outside PRINT_REPORT 2026-09 to 2026-10 | `reports.build_cost_centre_rows()` |
| 26 | Which cost centre? | The claimant's cost centre from employees.csv (not the approver's) | `reports.build_cost_centre_rows()` |
| 27 | Meaning of exception_total and rejected_total | exception_total = paid amount of EXCEPTION lines on APPROVED claims. rejected_total = rule-rejected lines on every claim, plus the whole claimed total of claims the approver REJECTED. Capped-off amounts (claimed minus allowed) are not counted as rejected | `reports.py` |
| 28 | Rows with no claims | Still written, with zeros: one row for every cost centre for every month asked | `reports.build_cost_centre_rows()` |
| 29 | Exchange rate missing for the exact expense date | Use the most recent EARLIER rate (up to 10 days back); if none, stop with a clear message | `rules.find_policy_rate()` |
| 30 | A hotel or per diem line in a city (or grade) with no cap in the tables | EXCEPTION with flag UNKNOWN_CITY_OR_GRADE, so a senior person looks at it instead of the program crashing | `rules.check_hotel()`, `rules.check_per_diem()` |
| 31 | Excel files (BOM, Windows line endings, blank cells, spaces) | Read as normal: BOM ignored, blank cell = "NA", spaces trimmed. Our output files use plain "\n" line endings | `loader.read_csv()` |
| 32 | What happens to a per diem claimed ABOVE the daily rate? (e.g. Rs 1,200 on tier 1) | EXCEPTION (BR-02), exactly like a hotel above its cap: E5 must approve, it is paid in full if approved, and the part above the rate is a taxable perquisite (Rs 200 in the example; Rs 450 for 1,200 on tier 2). Reason: the brief taxes domestic per diem above Rs 1,000, which only makes sense if such an amount can be paid. A FULL-day claim on a short travel day (under 8 hours) is not an exception: it is just CAPPED at the half rate. No line in the sample data is above its rate, so the sample outputs did not change | `rules.check_per_diem()` |
| 33 | Risk check: per diem vs meal on the same day in two DIFFERENT claims of one employee | Still decision #3 (same claim). Measured impact of the stricter reading (`PER_DIEM_MEAL_SCOPE = "EMPLOYEE"`): 7 per diem lines in 7 claims (CLM-005, 006, 032, 033, 036, 037, 038) become REJECTED and the total payout falls by Rs 6,000. To be confirmed with 10 SECONDS on the email thread. Change the setting if they answer differently | `PER_DIEM_MEAL_SCOPE` |

## Business rule numbers
- BR-01 Hotel cap (`rules.check_hotel`)
- BR-02 Per diem (`rules.check_per_diem`)
- BR-03 Travel class (`rules.check_travel`)
- BR-04 Receipts (`rules.check_receipts`)
- BR-05 Timeliness, 60 / 90 days (`rules.check_timeliness`)
- BR-06 Duplicates (`rules.check_duplicates`)
- BR-07 Team meals, attendees, alcohol (`rules.check_team_meal`)
- BR-08 Approval chain (`approvals.py`, refusals in `workflow.py`)
- BR-09 SLA and escalation (`calendar_rules.py`, `workflow.py`)
- BR-10 Currency conversion (`rules.convert_to_inr`)
- BR-11 Taxability (`rules.compute_taxable_amount`, totals in `settlement.py`)
- BR-12 Settlement (`settlement.py`)
