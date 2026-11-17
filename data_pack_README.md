# PS-029 – Corporate Expense Reimbursement Policy Engine with Approval Chains — Sample Data Pack

Prepared by 10 SECONDS for Team T041.

## Files

| File | What it holds | Row count |
|---|---|---|
| `employees.csv` | 25 employees with grade, role, cost centre, manager and base city | 25 |
| `cost_centres.csv` | Cost centres and their heads | 4 |
| `city_tiers.csv` | City → tier (1/2/3) for domestic cities; international cities carry tier INTL and a currency | 25 |
| `hotel_caps.csv` | Hotel cap per night by grade and city tier (0 = no cap) | 15 |
| `per_diem.csv` | Per-diem rates (meals and incidentals) when no itemised meals are claimed that day | 4 |
| `travel_entitlements.csv` | Travel class entitlement by grade | 5 |
| `holidays.csv` | Company holidays (Saturday and Sunday are non-working days as well) | 5 |
| `fx_rates.csv` | Policy exchange rates (INR per unit) per calendar day, 2026-07-01 to 2026-10-31 | 615 |
| `claims.csv` | 40 expense claims (header level) with trip reference and advance taken | 40 |
| `claim_lines.csv` | Claim lines (3–12 per claim) with category, date, amount, currency, receipt flag and category-specific attributes | 280 |
| `commands.txt` | Submission and approval actions (APPROVE / REJECT / RETURN / RESUBMIT / ON_LEAVE) over Sep–Oct 2026 | 152 |

Row count for `commands.txt` = command lines (comment lines starting with `#` and blank lines are not counted).

## Column reference

### employees.csv
| column | type | notes |
|---|---|---|
| employee_id | `EMP-001` … | |
| name, gender | string | gender `M`/`F` |
| grade | `E1`–`E5` | |
| role | `CEO` / `FINANCE_CONTROLLER` / `CC_HEAD` / `MANAGER` / `STAFF` | EMP-002 is the finance controller for every chain |
| cost_centre | `CC-000` … | FK → cost_centres |
| manager_id | employee_id or `NONE` | first approver; escalation goes to the approver's manager_id |
| base_city | string | |
| mobile | 10 digits | |

### cost_centres.csv — `cost_centre, name, head_employee_id` (the cost-centre head approver).
### city_tiers.csv — `city, country, tier (1/2/3/INTL), currency`.
### hotel_caps.csv — `grade, tier, cap_per_night` (Rs; 0 = no cap for E5).
### per_diem.csv — `scope (TIER1/TIER2/TIER3/INTL), rate, currency, half_day_rule`.
### travel_entitlements.csv — `grade, flight_up_to_4h, flight_over_4h, train`.
### holidays.csv — `date, name`; Saturdays and Sundays are also non-working.
### fx_rates.csv — `date, currency, rate_inr` policy rate (INR per 1 unit) for USD/EUR/GBP/SGD/AED, every calendar day 2026-07-01 … 2026-10-31.

### claims.csv
| column | type | notes |
|---|---|---|
| claim_id | `CLM-001` … | ids ascend in submission order |
| employee_id | FK | claimant |
| submitted_at | timestamp | equals the SUBMIT command timestamp |
| trip_ref | `TRP-###` or `TRP-SHARED` | claims on the same trip share a trip_ref |
| trip_city, trip_country | string | |
| trip_start, trip_end | date | |
| advance_amount | money | trip advance already paid to the employee (0.00 if none) |
| line_count | int | number of rows in claim_lines.csv |

### claim_lines.csv
| column | type | notes |
|---|---|---|
| claim_id, line_no | FK, int | line_no starts at 1 per claim |
| category | `HOTEL` `FLIGHT` `TRAIN` `TAXI` `MEAL` `PER_DIEM` `TEAM_MEAL` `CLIENT_ENTERTAINMENT` `ALCOHOL` `CONFERENCE` `MISC` | |
| expense_date | date | |
| amount | number | in `currency`; HOTEL amount is for all nights (divide by `nights` for the per-night check) |
| currency | `INR` `USD` `SGD` `AED` `GBP` `EUR` | |
| card_rate | number or `NA` | employee-supplied card statement rate (INR per unit) |
| receipt | `true`/`false` | |
| vendor | string | |
| city | string | city where the expense occurred (tier lookup) |
| nights | int or `NA` | HOTEL only |
| flight_hours | decimal hours or `NA` | FLIGHT only |
| travel_class | `ECONOMY` `BUSINESS` `2AC` `1AC` or `NA` | |
| entitled_fare | number or `NA` | entitled-class fare supplied by the employee, INR |
| hours_away | decimal or `NA` | PER_DIEM travel-day hours away from base (under 8 → half per diem) |
| attendees | `;`-separated list or `NA` | employee ids or `CLIENT:<name>`; anything else is invalid |
| description | string | |

`NA` marks a not-applicable attribute; it is never a missing required value.

## Command file format

One command per line, `COMMAND|arg1|...`, strictly in file order. `#` lines are comments. Timestamps are IST.

| command | arguments | meaning |
|---|---|---|
| `SUBMIT` | `claim_id`, `timestamp` | claim enters validation and its approval chain is built |
| `APPROVE` | `claim_id`, `approver_id`, `timestamp`, `comment` | current-step approval (reject the action if the approver is not the pending approver / escalated approver, is the claimant, or is a peer) |
| `REJECT` | `claim_id`, `approver_id`, `timestamp`, `reason` | claim rejected, terminal |
| `RETURN` | `claim_id`, `approver_id`, `timestamp`, `reason` | returned to the employee; SLA clock stops |
| `RESUBMIT` | `claim_id`, `timestamp`, `comment` | employee resubmits a RETURNED claim; chain restarts at step 1 with a fresh SLA |
| `ON_LEAVE` | `employee_id`, `from_date`, `to_date` | approver unavailable (inclusive dates) |
| `PRINT_REPORT` | `from_month`, `to_month` | emit the monthly cost-centre report |

SLA convention: 3 working days counted from the next working day after the step starts; breach is detected on the first working day after the deadline. Working days exclude Saturdays, Sundays and holidays.csv.

## Planted scenarios

Locators below are physical line numbers of the named file (a CSV header is line 1; comment lines in commands.txt count).

Edge cases from the brief (one bullet per edge case, in brief order):

- **Hotel line at exactly 150% of cap** — CLM-015 (EMP-011, grade E2, Mumbai tier 1, cap 4500.00/night): HOTEL line_no 6 (claim_lines.csv row 106) = 13500.00 for 2 nights = 6750.00 per night = exactly 150% of cap → EXCEPTION (payable only with E5 approval), not an outright rejection, which needs > 150%.
- **Claim line on day 60 and day 61 after expense** — CLM-013 submitted 2026-09-09 15:00:00: TAXI line_no 1 (claim_lines.csv row 89) dated 2026-07-11 (day 60 → allowed) and TAXI line_no 2 (claim_lines.csv row 90) dated 2026-07-10 (day 61 → EXCEPTION). Day count = submission date − expense date in calendar days.
- **Per diem claimed with a Rs 0 itemised meal line** — CLM-021: PER_DIEM 1000.00 and MEAL 0.00 both dated 2026-09-15 (line_no 5 (claim_lines.csv row 147), line_no 6 (claim_lines.csv row 148)). Decide (and state) whether a zero-amount itemised meal counts as an itemised claim that blocks the per diem.
- **Flight of exactly 4 hours for E4** — CLM-022 (EMP-005, E4): BUSINESS flight with flight_hours 4.00 and entitled_fare NA (line_no 7 (claim_lines.csv row 156)) → not 'over 4 hours', higher class without entitled fare → EXCEPTION; second BUSINESS line of 3.75 h with entitled_fare 7400.00 (line_no 8 (claim_lines.csv row 157)) → capped at 7400.00.
- **Fourth missing-receipt line of Rs 500.00** — CLM-027: five receipt=false lines ≤ 500 (line_no 3 (claim_lines.csv row 184), line_no 4 (claim_lines.csv row 185), line_no 5 (claim_lines.csv row 186), line_no 6 (claim_lines.csv row 187), line_no 7 (claim_lines.csv row 188)); the 4th (exactly 500.00, which itself needs no receipt) and the 5th must be rejected, the first three allowed.
- **Approver on leave making SLA breach land on a holiday** — CLM-023 SUBMIT at line 87 (2026-09-28 10:00, Monday); first approver EMP-009 is ON_LEAVE 2026-09-28 to 2026-10-05 (line 85). 3 working days after 28 Sep → deadline end of Thu 2026-10-01; the breach day Fri 2026-10-02 is Gandhi Jayanti (holidays.csv) and 3–4 Oct is the weekend → auto-escalation to EMP-004, who approves on 2026-10-06 (line 100). State on which day your engine records the escalation.
- **Card rate differing from policy by exactly 2.0%** — CLM-018: HOTEL 720.00 USD dated 2026-09-10 with card_rate 85.17 (line_no 7 (claim_lines.csv row 131)); fx_rates.csv policy USD rate on 2026-09-10 is 83.50 → 85.17 / 83.50 − 1 = 2.00% exactly → 'within 2%' → card rate applies. TAXI 42.00 USD with card_rate 85.30 (2.16% above) → policy rate.
- **Advance larger than the approved claim** — CLM-029 (EMP-016): advance_amount 40000.00 in claims.csv while the lines total ≈ 5014.00 → after approval the unspent advance must be recovered from salary and payout is 0.

Extra traps:

- Duplicate detection: CLM-019 MEAL 780.50 on 2026-08-25 duplicates CLM-006 MEAL 780.00 same employee/date/category within ±Rs 1 → reject the later line. CLM-006 and CLM-008 (trip TRP-SHARED) both claim TAXI 650.00 from Meru Cabs on 2026-08-24 → flag for the approver (not reject).
- CLM-031 (EMP-008, E3): TEAM_MEAL with 11 attendees at 1150.00/head (≤ 1200 cap, but > 10 attendees → needs E4 approval); ALCOHOL line → rejected; CLIENT_ENTERTAINMENT by E3 with drinks → allowed; TEAM_MEAL with attendee 'Vikram (friend)' (neither employee nor CLIENT-tagged) → rejected.
- Chain boundaries: CLM-026 totals exactly 10000.00 (manager only); CLM-012 totals exactly 50000.00 (manager + cost-centre head, no finance controller).
- Invalid approvals: CLM-006 is APPROVEd by its own claimant EMP-017 at line 19 (self-approval → reject the action); CLM-001 is APPROVEd by EMP-007 at line 4 who is not in its chain (peer → reject). Lines 11 and 12 are swapped out of timestamp order — process in file order.
- Several random claims carry hotel lines 5–40% above cap (EXCEPTION, E5 approval added to the chain) and PER_DIEM half-day travel days (hours_away 6.5 on the last day of international trips).

## What is NOT in this pack

Expected outputs are not provided for this set. Validate your engine with your own test suite against the rules in your brief (BR-01 … BR-nn). A separate hidden input set with the same schema will be used at final evaluation; outputs are compared field-for-field, so follow the column formats above exactly in your own output.


## Output format expected at evaluation

1. `line_decisions.csv` — one row per claim line: `claim_id, line_no, category, amount_inr, rate_used, decision (ALLOWED/CAPPED/EXCEPTION/REJECTED), allowed_amount, rule_ids (semicolon list), flags (semicolon list e.g. DUPLICATE_VENDOR_FLAG), taxable_amount`.
2. `audit_trail.csv` — one row per claim per command affecting it (SUBMIT and each APPROVE/REJECT/RETURN/RESUBMIT/escalation): `claim_id, line_no_in_commands, event, actor, timestamp, step_no, pending_approver, state_after (VALIDATING/PENDING_APPROVAL/RETURNED/REJECTED/APPROVED/PAID), chain (semicolon list of approver ids)`.
3. `claim_settlement.csv` — one row per claim: `claim_id, employee_id, claimed_total_inr, approved_total_inr, taxable_total_inr, advance_amount, advance_recovered_from_salary, net_payout, final_state, final_approval_at, pay_by_date`.
4. `cost_centre_report.csv` — one row per cost centre per month: `cost_centre, month (YYYY-MM), claims_count, approved_total_inr, exception_total_inr, rejected_total_inr, taxable_total_inr`.
