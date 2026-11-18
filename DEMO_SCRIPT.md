# 5-minute demo plan (Team T041, PS-029)

Record your screen with the VS Code terminal open in the project folder. Both of you can speak, one part each.

| Time | What to do on screen | What to say (simple words) |
|---|---|---|
| 0:00 to 0:30 | Show `README.md` | "This engine checks expense claims, builds the approval chain, runs the approval commands with the SLA clock, and settles the payout." |
| 0:30 to 1:15 | Run `python run_all_tests.py` | "121 automated tests, one per rule and every edge case in the brief. All pass." |
| 1:15 to 2:00 | Run `python main.py`, then `python verify_outputs.py` | "It processed 40 claims and 280 lines. The independent self-check reads only the output files and passes 26 of 26 checks." |
| 2:00 to 3:00 | Open `output/line_decisions.csv`: CLM-015 hotel row, CLM-027 4th receipt, CLM-022 flight | "Hotel at exactly 150% is an exception, not a rejection. The fourth missing receipt of Rs 500.00 is rejected. A flight of exactly 4 hours is not over 4 hours." |
| 3:00 to 4:00 | Open `output/audit_trail.csv`: CLM-023, then CLM-013 | "The approver was on leave and 2 October is a holiday, so the escalation is recorded on Monday 5 October. CLM-013 is returned after two breaches at the top because it has an exception line." |
| 4:00 to 4:40 | Open `output/claim_settlement.csv`: CLM-029, CLM-001 | "The advance of Rs 40,000 is bigger than the Rs 5,014 claim, so payout is 0 and Rs 34,986 is recovered. CLM-001 shows the taxable hotel excess." |
| 4:40 to 5:00 | Show `decision_log.md` | "Where the brief was open we made a choice and wrote it down. Each one is one setting in the code." |

Tips: zoom the terminal font so it is readable, keep each file open in a tab beforehand, and do one practice run first.
After uploading, paste the link into the "Video link" line in `README.md`.
