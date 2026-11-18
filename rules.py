"""
rules.py  -  the business rules (BR-xx). We add one rule at a time.

We use Decimal instead of normal decimal numbers (float) because money
must be EXACT. Example: with float, 85.17 / 83.50 - 1 gives
0.020000000000000018 which is NOT exactly 2%. Decimal avoids this.
"""
from decimal import Decimal, ROUND_HALF_UP


def D(value):
    """Turn a text/number into a Decimal safely."""
    return Decimal(str(value))


def money(value):
    """Round to 2 decimal places (paise), 0.005 rounds up."""
    return D(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------
# BR-CURRENCY : convert any amount to rupees
# Rule: use the policy rate of the EXPENSE DATE.
#       If the employee gave a card rate and it is within 2% of the
#       policy rate (exactly 2.0% counts as within), use the card rate.
#       Otherwise use the policy rate.
# ---------------------------------------------------------------
def find_policy_rate(fx_rates, currency, day):
    """Policy rate of the expense date. DECISION LOG #29: if that exact date is missing
    from fx_rates.csv (e.g. a holiday), use the most recent EARLIER rate (up to 10 days back)."""
    from datetime import date, timedelta
    when = date.fromisoformat(day)
    for back in range(0, 11):
        key = (currency, (when - timedelta(days=back)).isoformat())
        if key in fx_rates:
            return fx_rates[key]
    raise ValueError(f"No exchange rate for {currency} on or just before {day} in fx_rates.csv")


def convert_to_inr(line, fx_rates):
    """Return (amount_in_rupees, rate_used) for one claim line.

    line     : one row of claim_lines.csv
    fx_rates : {("USD", "2026-09-10"): 83.5, ...}
    """
    amount = D(line["amount"])

    # Rupees need no conversion
    if line["currency"] == "INR":
        return money(amount), Decimal("1")

    # Find the policy rate on the expense date
    policy_rate = D(find_policy_rate(fx_rates, line["currency"], line["expense_date"]))

    # Did the employee give a card rate?
    card_text = line["card_rate"]
    if card_text != "NA":
        card_rate = D(card_text)
        difference = abs(card_rate - policy_rate)
        allowed_difference = policy_rate * Decimal("0.02")   # 2% of policy
        if difference <= allowed_difference:                 # <= so 2.0% is OK
            return money(amount * card_rate), card_rate

    return money(amount * policy_rate), policy_rate


# ===============================================================
# STEP 3 : the result of checking one line, and the easy rules
# ===============================================================
# Each line ends with ONE decision. If two rules disagree, the
# MOST SERIOUS one wins:   ALLOWED < CAPPED < EXCEPTION < REJECTED
SEVERITY = {"ALLOWED": 0, "CAPPED": 1, "EXCEPTION": 2, "REJECTED": 3}

# Business rule numbers (use these same numbers in your design document)
BR_RECEIPT = "BR-04"       # receipts
BR_TIMELY = "BR-05"        # timeliness (60 / 90 days)

RECEIPT_LIMIT = Decimal("500")     # lines above Rs 500 need a receipt
MAX_NO_RECEIPT_LINES = 3           # at most 3 small lines without receipt


def new_result(line, amount_inr, rate_used):
    """Start a result for one line: everything is ALLOWED until a rule says otherwise."""
    return {
        "claim_id": line["claim_id"],
        "line_no": line["line_no"],
        "category": line["category"],
        "amount_inr": amount_inr,
        "rate_used": rate_used,
        "decision": "ALLOWED",
        "allowed_amount": amount_inr,
        "rule_ids": [],
        "flags": [],
        "taxable_amount": Decimal("0.00"),
    }


def apply_decision(result, decision, rule_id, allowed_amount=None):
    """Record what a rule decided. A more serious decision replaces a milder one.
    The rule id is always added to the list, so we can explain it later."""
    if rule_id not in result["rule_ids"]:
        result["rule_ids"].append(rule_id)
    if SEVERITY[decision] > SEVERITY[result["decision"]]:
        result["decision"] = decision
    # Work out the money that can be paid
    if result["decision"] == "REJECTED":
        result["allowed_amount"] = Decimal("0.00")
    elif allowed_amount is not None and decision == "CAPPED":
        # a cap always reduces the payable amount, even if the line is also an EXCEPTION
        result["allowed_amount"] = min(result["allowed_amount"], money(allowed_amount))


# ---------------------------------------------------------------
# BR-05 : timeliness
# days = submission date - expense date (calendar days)
#   0..60  -> fine          61..90 -> EXCEPTION        over 90 -> REJECTED
# ---------------------------------------------------------------
def check_timeliness(result, line, claim):
    from datetime import date
    submitted = date.fromisoformat(claim["submitted_at"][:10])
    expense = date.fromisoformat(line["expense_date"])
    days = (submitted - expense).days

    if days > 90:
        apply_decision(result, "REJECTED", BR_TIMELY)
    elif days > 60:
        apply_decision(result, "EXCEPTION", BR_TIMELY)


# ---------------------------------------------------------------
# BR-04 : receipts   (works on the WHOLE claim, because of the "3 lines" rule)
#   - PER_DIEM never has a receipt, so it is exempt.
#   - No receipt and amount > Rs 500        -> REJECTED
#   - No receipt and amount <= Rs 500       -> allowed, but only the first 3
#     such lines in the claim. The 4th, 5th ... are REJECTED.
# ---------------------------------------------------------------
def check_receipts(results, lines):
    """results and lines are lists in the same order (one per line of ONE claim)."""
    small_no_receipt_count = 0
    for result, line in zip(results, lines):
        if line["category"] == "PER_DIEM" or line["receipt"] == "true":
            continue
        if result["amount_inr"] > RECEIPT_LIMIT:
            apply_decision(result, "REJECTED", BR_RECEIPT)
        else:
            small_no_receipt_count += 1
            if small_no_receipt_count > MAX_NO_RECEIPT_LINES:
                apply_decision(result, "REJECTED", BR_RECEIPT)


# ===============================================================
# STEP 4A : hotel cap  (BR-01)
# ===============================================================
BR_HOTEL = "BR-01"

# DECISION LOG #1: hotel_caps.csv has no cap for international (INTL) cities.
# We decided: no cap is defined, so no hotel cap check is applied there.
# (Change this to "TIER1" if you want INTL hotels checked like tier-1 cities.)
INTL_HOTEL_RULE = "NO_CAP"


def check_hotel(result, line, grade, city_tiers, hotel_caps):
    """Hotel rule, per night:
         per night <= cap                -> ALLOWED
         cap < per night <= 150% of cap  -> EXCEPTION (needs E5 approval)
         per night > 150% of cap         -> REJECTED
       E5 has cap 0 in the table, which means NO cap.

       city_tiers : from load_city_tiers()   {"Mumbai": {... "tier": "1"}}
       hotel_caps : from load_hotel_caps()   {("E2", "1"): 4500.0}
    """
    if line["category"] != "HOTEL":
        return

    if line["city"] not in city_tiers or (grade, city_tiers[line["city"]]["tier"]) not in hotel_caps \
            and city_tiers[line["city"]]["tier"] != "INTL":
        # DECISION LOG #30: a city or grade we have no cap for cannot be checked, so a senior
        # person must look at it: EXCEPTION, with the flag UNKNOWN_CITY_OR_GRADE.
        apply_decision(result, "EXCEPTION", BR_HOTEL)
        result["flags"].append("UNKNOWN_CITY_OR_GRADE")
        return
    tier = city_tiers[line["city"]]["tier"]          # "1", "2", "3" or "INTL"
    if tier == "INTL":
        if INTL_HOTEL_RULE == "NO_CAP":
            return
        tier = "1"

    cap_per_night = D(hotel_caps[(grade, tier)])
    if cap_per_night == 0:                            # E5: no cap
        return

    nights = int(line["nights"])
    total_cap = cap_per_night * nights                # cap for the whole stay
    amount = result["amount_inr"]

    # We compare TOTALS (not per-night) so rounding can never spoil the
    # "exactly 150%" case.
    if amount > total_cap * Decimal("1.5"):
        apply_decision(result, "REJECTED", BR_HOTEL)
    elif amount > total_cap:
        apply_decision(result, "EXCEPTION", BR_HOTEL)
        # Remember how much is above the cap: this part becomes taxable later (BR-11)
        result["cap_excess"] = amount - total_cap


# ===============================================================
# STEP 4B : per diem  (BR-02)
# ===============================================================
BR_PER_DIEM = "BR-02"

# Which categories count as "itemised meals" that block a per diem?
ITEMISED_MEAL_CATEGORIES = ("MEAL", "TEAM_MEAL")

# DECISION LOG #2: a MEAL line of Rs 0 (CLM-021) is NOT a real claim,
# nothing was spent, so it does NOT block the per diem.
# (Set to True if you decide a Rs 0 meal line still blocks the per diem.)
ZERO_MEAL_BLOCKS_PER_DIEM = False

HALF_DAY_HOURS = Decimal("8")      # under 8 hours away -> half per diem


def has_itemised_meal(lines_same_day):
    """lines_same_day = all lines of THIS employee on THIS date (any claim).
    True if at least one itemised meal is claimed."""
    for line in lines_same_day:
        if line["category"] in ITEMISED_MEAL_CATEGORIES:
            if D(line["amount"]) > 0 or ZERO_MEAL_BLOCKS_PER_DIEM:
                return True
    return False


def check_per_diem(result, line, city_tiers, per_diem_rates, lines_same_day):
    """Per diem rule:
       1. If the employee also claimed itemised meals that day -> REJECTED.
       2. Daily rate: tier 1 = 1000, tier 2/3 = 750, international = 50 USD.
       3. Travel day under 8 hours away -> half the rate.
       4. Claimed more than a full day's rate -> EXCEPTION (taxable excess, BR-11).
          Claimed a full day on a short travel day -> CAPPED at the half rate.

       per_diem_rates : from load_per_diem()  {"TIER1": 1000.0, "INTL": 50.0}
    """
    if line["category"] != "PER_DIEM":
        return

    # 1. per diem and itemised meals cannot both be claimed
    if has_itemised_meal(lines_same_day):
        apply_decision(result, "REJECTED", BR_PER_DIEM)
        return

    # 2. daily rate (in the currency of the line: INR for India, USD abroad)
    if line["city"] not in city_tiers:
        apply_decision(result, "EXCEPTION", BR_PER_DIEM)           # DECISION LOG #30
        result["flags"].append("UNKNOWN_CITY_OR_GRADE")
        return
    tier = city_tiers[line["city"]]["tier"]
    scope = "INTL" if tier == "INTL" else "TIER" + tier
    daily_rate = D(per_diem_rates[scope])

    result["per_diem_domestic"] = (tier != "INTL")      # used by the tax rule (BR-11)
    full_limit_inr = money(daily_rate * result["rate_used"])

    # 3. half per diem on short travel days
    if line["hours_away"] != "NA" and D(line["hours_away"]) < HALF_DAY_HOURS:
        daily_rate = daily_rate / 2

    # 4. compare with the limit for THIS day (converted with the same rate as the claim)
    limit_inr = money(daily_rate * result["rate_used"])
    amount = result["amount_inr"]
    if amount > full_limit_inr:
        # DECISION LOG #32: more than a FULL day's rate is beyond the policy cap, so it is an
        # EXCEPTION (needs E5), exactly like a hotel above its cap. It is payable if approved,
        # and the part above the day's limit is a taxable perquisite (BR-11).
        apply_decision(result, "EXCEPTION", BR_PER_DIEM)
        result["cap_excess"] = amount - limit_inr
    elif amount > limit_inr:
        # claimed a full day on a short travel day (under 8 hours): just reduced to half
        apply_decision(result, "CAPPED", BR_PER_DIEM, allowed_amount=limit_inr)


# DECISION LOG #3: which lines count as "same day" for the per diem / meal clash?
#   "CLAIM"    -> only lines in the SAME claim            (our default)
#   "EMPLOYEE" -> lines of the same employee in ANY claim (stricter reading)
PER_DIEM_MEAL_SCOPE = "CLAIM"


def lines_for_meal_check(all_claims, claim, line):
    """Return the lines that count as 'same day' for this PER_DIEM line,
    following PER_DIEM_MEAL_SCOPE. Use it like this in Step 5:
        same_day = lines_for_meal_check(claims, claim, line)
        check_per_diem(result, line, tiers, rates, same_day)"""
    if PER_DIEM_MEAL_SCOPE == "CLAIM":
        pool = claim["lines"]
    else:
        pool = [l for c in all_claims.values()
                if c["employee_id"] == claim["employee_id"] for l in c["lines"]]
    return [l for l in pool if l["expense_date"] == line["expense_date"]]


# ===============================================================
# STEP 4C : travel class  (BR-03)
# ===============================================================
BR_TRAVEL = "BR-03"

# A bigger number = a more expensive class
CLASS_RANK = {"ECONOMY": 1, "BUSINESS": 2,      # flights
              "2AC": 1, "1AC": 2}               # trains

FLIGHT_LONG_HOURS = Decimal("4")                # business is only for flights OVER 4 hours


def check_travel(result, line, grade, travel_entitlements):
    """Travel class rule:
       - Find the class this grade is entitled to
         (flights: over 4 hours is a 'long' flight; exactly 4.00 is NOT long).
       - Claimed class is the same or lower     -> ALLOWED
       - Claimed class is HIGHER:
            entitled_fare is given  -> CAPPED at that fare
            entitled_fare is 'NA'   -> EXCEPTION

       travel_entitlements : from load_travel_entitlements()
    """
    if line["category"] not in ("FLIGHT", "TRAIN"):
        return

    row = travel_entitlements[grade]
    if line["category"] == "TRAIN":
        entitled_class = row["train"]
    else:
        hours = D(line["flight_hours"]) if line["flight_hours"] != "NA" else Decimal("0")
        entitled_class = row["flight_over_4h"] if hours > FLIGHT_LONG_HOURS else row["flight_up_to_4h"]

    claimed_class = line["travel_class"]
    if CLASS_RANK[claimed_class] <= CLASS_RANK[entitled_class]:
        return                                           # same or lower class: fine

    # Claimed a higher class than allowed
    if line["entitled_fare"] != "NA":
        fare_limit = money(D(line["entitled_fare"]) * result["rate_used"])
        if result["amount_inr"] > fare_limit:
            apply_decision(result, "CAPPED", BR_TRAVEL, allowed_amount=fare_limit)
    else:
        apply_decision(result, "EXCEPTION", BR_TRAVEL)


# ===============================================================
# STEP 4D : team meals, attendees and alcohol  (BR-07)
# ===============================================================
BR_TEAM_MEAL = "BR-07"

MEAL_CAP_PER_HEAD = Decimal("1200")
BIG_GROUP_LIMIT = 10                      # MORE than 10 attendees -> needs E4 approval
ALCOHOL_WORDS = ("alcohol", "drink", "liquor", "wine", "beer")   # DECISION LOG #4


def grade_number(grade):
    """'E3' -> 3  (so we can say grade >= E3)"""
    return int(grade[1:])


def split_attendees(line):
    """'EMP-003;EMP-005;CLIENT:Ravi' -> ['EMP-003', 'EMP-005', 'CLIENT:Ravi']"""
    if line["attendees"] == "NA":
        return []
    return line["attendees"].split(";")


def check_team_meal(result, line, grade, employees):
    """Rules for meals with other people and for alcohol:
       1. Every attendee must be an employee or tagged CLIENT   -> else REJECTED
       2. Alcohol is REJECTED, unless the line is CLIENT_ENTERTAINMENT
          claimed by grade E3 or higher.
       3. TEAM_MEAL: Rs 1,200 per attendee cap  -> CAPPED at 1200 x attendees
       4. TEAM_MEAL with MORE than 10 attendees -> allowed, but needs E4 approval
          (we add the flag NEEDS_E4_APPROVAL; approvals.build_chain uses it)

       employees : from load_employees()
    """
    attendees = split_attendees(line)

    # 1. attendee check (for any line that lists attendees)
    for who in attendees:
        if who not in employees and not who.startswith("CLIENT"):
            apply_decision(result, "REJECTED", BR_TEAM_MEAL)
            return

    # 2. alcohol check
    text = line["description"].lower()
    is_alcohol = line["category"] == "ALCOHOL" or any(w in text for w in ALCOHOL_WORDS)
    if is_alcohol:
        allowed = line["category"] == "CLIENT_ENTERTAINMENT" and grade_number(grade) >= 3
        if not allowed:
            apply_decision(result, "REJECTED", BR_TEAM_MEAL)
            return

    # 3 and 4: only for TEAM_MEAL lines
    if line["category"] != "TEAM_MEAL" or not attendees:
        return

    cap = MEAL_CAP_PER_HEAD * len(attendees)
    if result["amount_inr"] > cap:
        apply_decision(result, "CAPPED", BR_TEAM_MEAL, allowed_amount=cap)

    if len(attendees) > BIG_GROUP_LIMIT:
        apply_decision(result, "ALLOWED", BR_TEAM_MEAL)       # just records the rule id
        result["flags"].append("NEEDS_E4_APPROVAL")


# ===============================================================
# STEP 4E : duplicate detection  (BR-06)
# ===============================================================
BR_DUPLICATE = "BR-06"
DUPLICATE_TOLERANCE = Decimal("1")          # +/- Rs 1


def check_duplicates(all_claims, results_by_key):
    """Two duplicate rules. This one needs ALL claims, not just one.

    results_by_key : {(claim_id, position_in_claim): result}
    We use the POSITION of the line in its claim, because line_no is not
    unique in the sample data.

    Rule A (REJECT): same employee + same date + same category + same amount
        (within +/- Rs 1), in ANY claim. The LATER line is rejected; the
        earlier one stays. 'Later' = earlier submission time first, and for
        the same claim, the earlier line.
    Rule B (FLAG): same trip_ref, same vendor, same amount, but two DIFFERENT
        employees -> both lines get the flag DUPLICATE_VENDOR_FLAG for the
        approver. The decision does not change.
    """
    # claims in order of submission (then claim id) so 'earlier' makes sense
    ordered = sorted(all_claims.values(), key=lambda c: (c["submitted_at"], c["claim_id"]))

    # ---------- Rule A ----------
    seen = []        # earlier lines: (employee, date, category, amount)
    for claim in ordered:
        for pos, line in enumerate(claim["lines"]):
            result = results_by_key[(claim["claim_id"], pos)]
            who, day, cat = claim["employee_id"], line["expense_date"], line["category"]
            amount = result["amount_inr"]
            if any(w == who and d == day and c == cat and abs(a - amount) <= DUPLICATE_TOLERANCE
                   for (w, d, c, a) in seen):
                apply_decision(result, "REJECTED", BR_DUPLICATE)
            seen.append((who, day, cat, amount))

    # ---------- Rule B ----------
    lines_by_trip = {}
    for claim in ordered:
        for pos, line in enumerate(claim["lines"]):
            if line["vendor"] in ("NA", ""):
                continue
            lines_by_trip.setdefault(claim["trip_ref"], []).append((claim["employee_id"], line["vendor"], pos, claim["claim_id"]))

    for trip, entries in lines_by_trip.items():
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                emp_a, vendor_a, pos_a, claim_a = entries[i]
                emp_b, vendor_b, pos_b, claim_b = entries[j]
                if emp_a == emp_b or vendor_a != vendor_b:
                    continue
                res_a = results_by_key[(claim_a, pos_a)]
                res_b = results_by_key[(claim_b, pos_b)]
                if res_a["amount_inr"] == res_b["amount_inr"]:
                    for res in (res_a, res_b):
                        if "DUPLICATE_VENDOR_FLAG" not in res["flags"]:
                            res["flags"].append("DUPLICATE_VENDOR_FLAG")


# ===============================================================
# BR-11 : taxable amount of ONE line  (reported only; settlement counts it for APPROVED claims)
# ===============================================================
BR_TAX = "BR-11"
PER_DIEM_TAX_FREE_LIMIT = Decimal("1000")      # domestic per diem above Rs 1,000 a day is taxable


def compute_taxable_amount(result):
    """Two clauses of the brief:
       1. Reimbursement beyond a policy cap that is approved as an EXCEPTION is a taxable
          perquisite: the part ABOVE THE CAP (hotel, per diem).   -> cap_excess
       2. Domestic per diem above Rs 1,000 per day is taxable:     -> paid amount minus 1,000
          (clause 2 is data driven: it matters if per_diem.csv ever allows more than 1,000.)
       A rejected line is not paid, so nothing is taxable."""
    taxable = Decimal("0.00")
    if result["decision"] == "REJECTED":
        return taxable
    if result["decision"] == "EXCEPTION":
        taxable = result.get("cap_excess", Decimal("0.00"))
    if result["category"] == "PER_DIEM" and result.get("per_diem_domestic"):
        taxable = max(taxable, result["allowed_amount"] - PER_DIEM_TAX_FREE_LIMIT)
    return money(max(taxable, Decimal("0.00")))
