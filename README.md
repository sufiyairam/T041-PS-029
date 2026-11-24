# T041-PS-029: Corporate Expense Reimbursement Policy Engine

**Team T041** · St Shifana Sanobar (1AT24CD083) and Sufiya Iram (1AT24CD084) · Section CSDS B
**Problem statement:** PS-029, Corporate Expense Reimbursement Policy Engine with Approval Chains (BFSI, Corporate Finance)
**Language:** Python 3.10 or newer (tested on Python 3.12). No extra libraries are needed.

---

## Demo video (5 minutes)

**Video link: ADD THE LINK HERE AFTER RECORDING** (for example a YouTube "unlisted" or Google Drive link, with sharing turned on).
The recording plan is in https://drive.google.com/file/d/1kxkswRfNmAxfRn1c0qVilyph15xDjxRH/view?usp=sharing

---

## 1. What this project does

A company's finance team receives expense claims from employees. This program does the finance team's work automatically. It is command-file driven and has no UI.

1. **Checks every expense line** against the company rules (hotel caps, per diem, travel class, receipts, claim age, duplicates, team meals, alcohol, currency).
2. **Builds the approval chain** (who must approve, in what order).
3. **Processes the commands** in `commands.txt` (SUBMIT, APPROVE, REJECT, RETURN, RESUBMIT, ON_LEAVE, PRINT_REPORT), including the 3-working-day SLA and automatic escalation.
4. **Settles each claim:** taxable amount, advance netting, payout and pay-by date.
5. **Writes reports:** a decision for every line, an audit trail, a settlement file and a monthly cost-centre report.

## 2. How to run it

You need Python 3.10 or newer. Open a terminal in the project folder (in VS Code: Terminal → New Terminal).

```
python main.py
```

It reads the files in the `data` folder and writes the results to the `output` folder.

To use other folders:

```
python main.py  <data_folder>  <output_folder>
```

Other useful commands:

| Command | What it does |
|---|---|
| `python run_all_tests.py` | Runs all 121 tests. The last line should say `OK`. |
| `python verify_outputs.py` | Independent self-check of the output files (26 checks, including the 8 edge cases in the brief). Run `python main.py` first. |
| `python show_chains.py` | Prints the approval chain of every claim. |

## 3. Input files (in `data/`)

| File | Content |
|---|---|
| `employees.csv` | 25 employees: grade (E1 to E5), cost centre, manager, base city |
| `cost_centres.csv` | cost centres and their heads |
| `city_tiers.csv` | city tier (1, 2, 3 or INTL) |
| `hotel_caps.csv` | hotel cap per night by grade and tier |
| `per_diem.csv` | daily food allowance by tier |
| `travel_entitlements.csv` | flight and train class by grade |
| `fx_rates.csv` | policy exchange rate per currency per day |
| `holidays.csv` | company holidays (used for working days) |
| `claims.csv` | 40 claims (header level, with trip reference and advance) |
| `claim_lines.csv` | 280 expense lines |
| `commands.txt` | 152 commands, processed strictly in file order |

Files saved from Excel ("CSV UTF-8"), Windows line endings, extra spaces and blank cells (read as "not applicable") are all handled.

## 4. Output files (in `output/`)

| File | One row per | Main columns |
|---|---|---|
| `line_decisions.csv` | claim line | decision (ALLOWED, CAPPED, EXCEPTION, REJECTED), allowed amount, rule IDs, flags, taxable amount |
| `audit_trail.csv` | event on a claim | event, actor, timestamp, step number, pending approver, state after, chain |
| `claim_settlement.csv` | claim | claimed, approved and taxable totals, advance, amount recovered from salary, net payout, final state, pay-by date |
| `cost_centre_report.csv` | cost centre per month | claims count, approved, exception, rejected and taxable totals |
| `rejected_commands.csv` | refused command | our own extra file: self-approvals, peer approvals and other invalid commands, with the reason |

## 5. Business rules (BR numbers used in rule IDs and in the design document)

| ID | Rule | Code |
|---|---|---|
| BR-01 | **Hotel cap** per night by grade and city tier. Above cap is EXCEPTION, above 150% of cap is REJECTED, E5 has no cap | `rules.check_hotel` |
| BR-02 | **Per diem**: Rs 1,000 tier 1, Rs 750 tier 2/3, USD 50 abroad. Half on travel days under 8 hours. Cannot be claimed together with itemised meals the same day. Above a full day's rate is an EXCEPTION; a full-day claim on a short travel day is CAPPED at the half rate | `rules.check_per_diem` |
| BR-03 | **Travel class**: higher class is CAPPED at the entitled fare, or EXCEPTION if no fare is given. Business only for E4/E5 on flights over 4 hours | `rules.check_travel` |
| BR-04 | **Receipts**: needed above Rs 500. At most 3 lines of Rs 500 or less may have no receipt, the 4th and later are rejected | `rules.check_receipts` |
| BR-05 | **Timeliness**: up to 60 days fine, 61 to 90 days EXCEPTION, over 90 days REJECTED | `rules.check_timeliness` |
| BR-06 | **Duplicates**: same employee, date, category and amount (within Rs 1) is rejected. Same vendor and amount by two employees on one trip is flagged | `rules.check_duplicates` |
| BR-07 | **Team meals and alcohol**: Rs 1,200 per attendee, attendees must be employees or CLIENT, more than 10 attendees needs E4, alcohol rejected unless CLIENT_ENTERTAINMENT by E3 or above | `rules.check_team_meal` |
| BR-08 | **Approval chain**: up to Rs 10,000 manager. Up to Rs 50,000 manager and cost-centre head. Above that the finance controller too. Any EXCEPTION adds E5. Nobody approves their own claim or a peer's | `approvals.py` |
| BR-09 | **SLA**: 3 working days per approver, then automatic escalation to their manager. Two breaches in a row at the top auto-approve (no exception lines) or return (exception lines). RETURN stops the clock and RESUBMIT restarts it | `workflow.py`, `calendar_rules.py` |
| BR-10 | **Currency**: policy rate of the expense date. A card rate within 2% (2.0% included) is used instead | `rules.convert_to_inr` |
| BR-11 | **Taxability**: the part of an approved EXCEPTION above its cap (hotel or per diem) is a taxable perquisite, and so is domestic per diem above Rs 1,000 a day. Reported per claim, not deducted from the payout | `rules.compute_taxable_amount`, `settlement.py` |
| BR-12 | **Settlement**: advance is netted first. If the advance is larger, the payout is 0 and the rest is recovered from salary. Pay within 5 working days of final approval | `settlement.py` |

## 6. Edge cases from the brief, and where they are tested

| Edge case | Claim | Result |
|---|---|---|
| Hotel at exactly 150% of cap | CLM-015 | EXCEPTION (not rejected) |
| Line on day 60 and on day 61 | CLM-013 | day 60 ALLOWED, day 61 EXCEPTION |
| Per diem with a Rs 0 meal line | CLM-021 | per diem ALLOWED |
| E4 flight of exactly 4 hours | CLM-022 | business class is EXCEPTION |
| 4th missing-receipt line of Rs 500.00 | CLM-027 | REJECTED |
| Approver on leave, SLA breach lands on a holiday | CLM-023 | escalated on Monday 5 Oct (2 Oct is a holiday) |
| Card rate exactly 2.0% from policy | CLM-018 | card rate used |
| Advance larger than the approved claim | CLM-029 | payout 0, Rs 34,986 recovered |

## 7. Project structure

```
T041-PS-029/
  main.py              run this: validate, process commands, settle, report
  loader.py            reads the input files
  paths.py             data and output folder locations
  rules.py             line rules BR-01 to BR-07 and currency (BR-10)
  pipeline.py          runs all line rules on every line, writes line_decisions.csv
  approvals.py         approval chain (BR-08)
  calendar_rules.py    working days and SLA dates (BR-09)
  workflow.py          command processor, SLA, escalation, audit trail (BR-09)
  settlement.py        taxable, advance netting, payout (BR-11, BR-12)
  reports.py           monthly cost-centre report
  verify_outputs.py    independent self-check of the output files
  show_chains.py       prints every claim's approval chain
  run_all_tests.py     runs the whole test suite
  decision_log.md      every choice we made where the brief was unclear
  data/                input files
  output/              result files
  tests/               121 automated tests
```

## 8. Decision log

The brief leaves some points open (for example, hotel caps for international cities, or whether a Rs 0 meal blocks a per diem). We made a choice for each one and recorded it in [`decision_log.md`](decision_log.md). Most are a single setting at the top of a code file (for example `INTL_HOTEL_RULE` in `rules.py`), so they can be changed in seconds.

## 9. Design choices worth knowing

- **Money uses `Decimal`, not `float`.** With normal decimals, 2.00% can come out as 2.0000000000000018%, which would break the "exactly 2.0%" rule.
- **Rules are small separate functions**, one per business rule, so each can be tested and changed alone.
- **The strongest decision on a line wins:** ALLOWED < CAPPED < EXCEPTION < REJECTED. Every rule that fires adds its rule ID, so every decision can be explained.
- **Commands are processed strictly in file order**, and the SLA clock advances to each command's timestamp before it runs.
- **`line_no` is not unique** in the sample data (CLM-015, 018, 021 and 022 repeat a number), so lines are identified by their position in the claim.
