"""
calendar_rules.py  -  working days and the SLA clock  (BR-09)

Working day = Monday to Friday that is NOT in holidays.csv.

SLA rule from the README:
  * An approver has 3 working days.
  * Counting starts from the NEXT working day after the step starts.
  * The breach is noticed on the FIRST working day AFTER the deadline.

Example (CLM-023): step starts Mon 28 Sep.
   day 1 = Tue 29 Sep, day 2 = Wed 30 Sep, day 3 = Thu 1 Oct  -> deadline = Thu 1 Oct
   Fri 2 Oct is a holiday, 3-4 Oct is a weekend -> breach day = Mon 5 Oct
"""
from datetime import timedelta

SLA_WORKING_DAYS = 3


def is_working_day(day, holidays):
    """day is a datetime.date; holidays is a set of 'YYYY-MM-DD' strings."""
    return day.weekday() < 5 and day.isoformat() not in holidays


def next_working_day(day, holidays):
    """The first working day AFTER `day`."""
    day = day + timedelta(days=1)
    while not is_working_day(day, holidays):
        day = day + timedelta(days=1)
    return day


def add_working_days(day, count, holidays):
    for _ in range(count):
        day = next_working_day(day, holidays)
    return day


def sla_deadline(start_day, holidays):
    """The last day the approver can act in time (end of that day)."""
    return add_working_days(start_day, SLA_WORKING_DAYS, holidays)


def breach_day(start_day, holidays):
    """The day the engine notices the breach and escalates."""
    return next_working_day(sla_deadline(start_day, holidays), holidays)
