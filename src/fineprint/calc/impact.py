"""Turn a risky clause into rupees. Pure, deterministic Python: no language model is involved.

Each category has one function. Numbers come from the clause (extract/money.py) and from the
document context, which the user can edit in the UI. Every result states its assumptions.
"""
from __future__ import annotations

import re

from ..extract.money import inr
from ..schemas import ClauseFields, LoanContext, Money, Percent, RupeeImpact

GST_RATE = 0.18


def emi(principal: float, annual_rate: float, months: int) -> float:
    """Standard reducing-balance EMI: P·r·(1+r)^n / ((1+r)^n − 1)."""
    if months <= 0:
        raise ValueError("tenure must be positive")
    r = annual_rate / 12 / 100
    if r == 0:
        return principal / months
    f = (1 + r) ** months
    return principal * r * f / (f - 1)


def _gst(amount: float, fields: ClauseFields) -> tuple[float, list[str]]:
    if fields.plus_gst:
        return amount * (1 + GST_RATE), [f"Includes 18% GST, because the clause says tax is extra ({inr(amount)} + {inr(amount * GST_RATE)})."]
    return amount, []


def _nearest(items, pos: int):
    return min(items, key=lambda x: abs(x.start - pos)) if items else None


def _context_emi(ctx: LoanContext) -> tuple[float | None, str | None]:
    if ctx.emi:
        return ctx.emi, f"EMI of {inr(ctx.emi)} as stated in the document"
    if ctx.principal and ctx.annual_rate is not None and ctx.tenure_months:
        value = emi(ctx.principal, ctx.annual_rate, ctx.tenure_months)
        return value, f"EMI of {inr(value)} worked out from {inr(ctx.principal)} at {ctx.annual_rate:g}% for {ctx.tenure_months} months"
    return None, None


def _no_figure(basis: str) -> RupeeImpact:
    return RupeeImpact(headline=basis, amount=None, basis=basis)


def prepayment(fields: ClauseFields, ctx: LoanContext, pos: int, text: str) -> RupeeImpact:
    pct = _nearest(fields.percents, pos)
    flat = _nearest([a for a in fields.amounts if a.value < 1_000_000], pos)
    if pct and ctx.principal:
        prepay = round(ctx.principal / 2, -3) or ctx.principal
        charge, notes = _gst(prepay * pct.value / 100, fields)
        return RupeeImpact(
            headline=f"{inr(charge)} if you repay {inr(prepay)} early",
            amount=round(charge, 2),
            basis=f"{pct.value:g}% of the amount repaid early ({inr(prepay)}, half the loan, as an example).",
            assumptions=["Change the loan amount above to see your own case."] + notes,
        )
    if flat:
        charge, notes = _gst(flat.value, fields)
        return RupeeImpact(headline=f"{inr(charge)} to close the loan early", amount=round(charge, 2), basis=f"Fixed charge of {inr(flat.value)} stated in the clause.", assumptions=notes)
    if pct:
        return _no_figure(f"{pct.value:g}% of the amount you repay early. Add the loan amount above to see it in rupees.")
    return _no_figure("The clause does not say how much. Ask for the exact charge in writing before you sign.")


def floating(fields: ClauseFields, ctx: LoanContext, pos: int, text: str) -> RupeeImpact:
    if ctx.principal and ctx.annual_rate is not None and ctx.tenure_months:
        base = emi(ctx.principal, ctx.annual_rate, ctx.tenure_months)
        up = emi(ctx.principal, ctx.annual_rate + 1, ctx.tenure_months)
        extra_month = up - base
        total = extra_month * ctx.tenure_months
        return RupeeImpact(
            headline=f"+{inr(extra_month)} a month, +{inr(total)} in total, if the rate rises by 1 point",
            amount=round(total, 2),
            basis=f"EMI goes from {inr(base)} to {inr(up)} when the rate moves from {ctx.annual_rate:g}% to {ctx.annual_rate + 1:g}%.",
            assumptions=["Assumes the lender raises the EMI. Some lenders extend the tenure instead, which costs even more interest."],
        )
    return _no_figure("If rates rise, your EMI or tenure goes up. Add the loan amount, rate and tenure above to see it in rupees.")


def late_payment(fields: ClauseFields, ctx: LoanContext, pos: int, text: str) -> RupeeImpact:
    instalment, instalment_basis = _context_emi(ctx)
    pct = _nearest(fields.percents, pos)
    flat = _nearest([a for a in fields.amounts if a.value < 100_000], pos)
    if pct and instalment:
        monthly_pct = pct.value if pct.period != "year" else pct.value / 12
        charge, notes = _gst(instalment * monthly_pct / 100, fields)
        period_note = "" if pct.period != "year" else f" ({pct.value:g}% a year is {monthly_pct:.2f}% a month)"
        return RupeeImpact(
            headline=f"{inr(charge)} for each month one EMI stays unpaid",
            amount=round(charge, 2),
            basis=f"{monthly_pct:g}% a month on one overdue EMI{period_note}. {instalment_basis}.",
            assumptions=["If the clause is unclear, it may be charged on the whole overdue amount, which is higher."] + notes,
        )
    if len(fields.amounts) >= 3 and re.search(r"(?i)\b(?:between|above|up to|upto|slab|exceeds?)\b", text):
        return _no_figure("Depends on how much you owe: the fee goes up in slabs. See the clause for each slab.")
    if flat:
        charge, notes = _gst(flat.value, fields)
        return RupeeImpact(headline=f"{inr(charge)} each time you pay late", amount=round(charge, 2), basis=f"Fixed late fee of {inr(flat.value)} stated in the clause.", assumptions=notes)
    if pct:
        return _no_figure(f"{pct.value:g}% of the overdue amount. Add the loan amount, rate and tenure above to see it in rupees.")
    return _no_figure("The clause does not give the amount. Ask the lender for its schedule of charges.")


def bounce(fields: ClauseFields, ctx: LoanContext, pos: int, text: str) -> RupeeImpact:
    flat = _nearest([a for a in fields.amounts if a.value < 50_000], pos)
    if flat:
        charge, notes = _gst(flat.value, fields)
        return RupeeImpact(
            headline=f"{inr(charge)} every time an EMI bounces",
            amount=round(charge, 2),
            basis=f"Fixed bounce charge of {inr(flat.value)} stated in the clause.",
            assumptions=["Your own bank may charge a separate fee for the failed debit."] + notes,
        )
    return _no_figure("The bounce charge amount is not stated here. Ask for it in writing.")


def processing(fields: ClauseFields, ctx: LoanContext, pos: int, text: str) -> RupeeImpact:
    pct = _nearest(fields.percents, pos)
    amounts = fields.amounts
    minimum = _find_bound(text, amounts, r"min(?:imum)?\.?\s*(?:of)?")
    maximum = _find_bound(text, amounts, r"max(?:imum)?\.?\s*(?:of)?")
    if pct and ctx.principal:
        fee = ctx.principal * pct.value / 100
        notes: list[str] = []
        if minimum and fee < minimum:
            fee, notes = minimum, [f"Raised to the stated minimum of {inr(minimum)}."]
        if maximum and fee > maximum:
            fee, notes = maximum, [f"Capped at the stated maximum of {inr(maximum)}."]
        total, gst_notes = _gst(fee, fields)
        return RupeeImpact(
            headline=f"{inr(total)} taken upfront",
            amount=round(total, 2),
            basis=f"{pct.value:g}% of {inr(ctx.principal)}.",
            assumptions=notes + gst_notes + ["Often deducted from the amount you receive, so you get less cash but repay the full loan."],
        )
    flat = _nearest(amounts, pos)
    if flat:
        total, notes = _gst(flat.value, fields)
        return RupeeImpact(headline=f"{inr(total)} taken upfront", amount=round(total, 2), basis=f"Fixed fee of {inr(flat.value)} stated in the clause.", assumptions=notes)
    if pct:
        return _no_figure(f"{pct.value:g}% of the loan. Add the loan amount above to see it in rupees.")
    return _no_figure("The fee amount is not stated here. Ask for it before you sign.")


def _find_bound(text: str, amounts: list[Money], word: str) -> float | None:
    for m in re.finditer(word, text, re.IGNORECASE):
        after = [a for a in amounts if 0 <= a.start - m.end() < 25]
        if after:
            return after[0].value
    return None


def deferred_interest(fields: ClauseFields, ctx: LoanContext, pos: int, text: str) -> RupeeImpact:
    pct = _nearest([p for p in fields.percents if p.value > 0], pos)
    rate = (pct.value * 12 if pct and pct.period == "month" else pct.value) if pct else ctx.annual_rate
    months = ctx.tenure_months
    if not months and fields.durations:
        months = int(round(fields.durations[0].months))
    if rate and ctx.principal and months:
        interest = ctx.principal * rate / 100 * months / 12
        return RupeeImpact(
            headline=f"Up to {inr(interest)} in interest if the condition is missed",
            amount=round(interest, 2),
            basis=f"{rate:g}% a year on {inr(ctx.principal)} for {months} months, charged from the purchase date.",
            assumptions=["Simple-interest estimate. Read which condition triggers it: one missed or late instalment is common."],
        )
    flat = _nearest(fields.amounts, pos)
    if flat and ctx.principal and flat.value < ctx.principal:
        cost, notes = _gst(flat.value, fields)
        return RupeeImpact(headline=f"{inr(cost)} hidden cost on a '0% EMI'", amount=round(cost, 2), basis=f"Fee of {inr(flat.value)} stated in the clause, on a purchase of {inr(ctx.principal)}.", assumptions=notes)
    return _no_figure("Interest can be charged even though the offer says 0%. Add the purchase amount, rate and months above to see it in rupees.")


def bundled_insurance(fields: ClauseFields, ctx: LoanContext, pos: int, text: str) -> RupeeImpact:
    pct = _nearest(fields.percents, pos)
    flat = _nearest([a for a in fields.amounts if not ctx.principal or a.value < ctx.principal], pos)
    premium = None
    basis = ""
    if flat:
        premium, basis = flat.value, f"Premium of {inr(flat.value)} stated in the clause"
    elif pct and ctx.principal:
        premium, basis = ctx.principal * pct.value / 100, f"{pct.value:g}% of {inr(ctx.principal)}"
    if premium is None:
        return _no_figure("The premium is not stated here. Ask whether the cover is optional and what it costs.")
    if ctx.annual_rate and ctx.tenure_months:
        total = emi(premium, ctx.annual_rate, ctx.tenure_months) * ctx.tenure_months
        return RupeeImpact(
            headline=f"{inr(premium)} added to your loan, about {inr(total)} once interest is paid on it",
            amount=round(total, 2),
            basis=f"{basis}, repaid with interest at {ctx.annual_rate:g}% over {ctx.tenure_months} months.",
            assumptions=["Assumes the premium is financed as part of the loan."],
        )
    return RupeeImpact(headline=f"{inr(premium)} added to what you pay", amount=round(premium, 2), basis=basis + ".")


def recurring(fields: ClauseFields, ctx: LoanContext, pos: int, text: str) -> RupeeImpact:
    flat = _nearest(fields.amounts, pos)
    if not flat:
        return _no_figure("The fee amount is not stated here.")
    yearly = flat.value
    window = text[max(0, flat.start - 60): flat.end + 60].lower()
    per_month = bool(re.search(r"per month|monthly|every month|p\.?m\.?", window))
    if per_month:
        yearly = flat.value * 12
    total, notes = _gst(yearly, fields)
    label = "a year" if not per_month else f"a year ({inr(flat.value)} every month)"
    return RupeeImpact(headline=f"{inr(total)} {label}", amount=round(total, 2), basis=f"Fee of {inr(flat.value)} stated in the clause.", assumptions=notes + (["Check whether it is waived if you spend a minimum amount."] if "waiv" in text.lower() else []))


def auto_renewal(fields: ClauseFields, ctx: LoanContext, pos: int, text: str) -> RupeeImpact:
    flat = _nearest(fields.amounts, pos)
    if flat:
        total, notes = _gst(flat.value, fields)
        return RupeeImpact(headline=f"{inr(total)} charged again at each renewal unless you cancel", amount=round(total, 2), basis=f"Renewal price of {inr(flat.value)} stated in the clause.", assumptions=notes + ["Set a reminder a few days before the renewal date."])
    return _no_figure("You are charged again automatically. Note the renewal date and how to cancel.")


def minimum_due(fields: ClauseFields, ctx: LoanContext, pos: int, text: str) -> RupeeImpact:
    monthly = next((p.value for p in fields.percents if p.period == "month"), None)
    if monthly is None and ctx.annual_rate:
        monthly = ctx.annual_rate / 12
    if monthly is None:
        monthly = 3.75
        rate_note = "Assumes 3.75% a month, a typical card rate, because the clause does not state one."
    else:
        rate_note = f"Interest at {monthly:g}% a month."
    min_pct = 5.0
    near_min = [p for p in fields.percents if p.period == "unspecified" and p.value <= 10]
    if near_min:
        min_pct = near_min[0].value
    balance = min(ctx.principal, 50_000) if ctx.principal else 50_000
    months, interest = _simulate_minimum(balance, monthly, min_pct)
    years = months / 12
    if months >= 600:
        headline = f"Paying only the minimum on {inr(balance)} never clears it"
    else:
        headline = f"Paying only the minimum on {inr(balance)} takes {years:.1f} years and costs {inr(interest)} in interest"
    return RupeeImpact(
        headline=headline,
        amount=round(interest, 2),
        basis=f"Minimum due of {min_pct:g}% of the balance (at least ₹200) each month, no new spending.",
        assumptions=[rate_note],
    )


def _simulate_minimum(balance: float, monthly_rate: float, min_pct: float) -> tuple[int, float]:
    months, paid_interest = 0, 0.0
    while balance > 0.5 and months < 600:
        interest = balance * monthly_rate / 100
        balance += interest
        paid_interest += interest
        payment = min(balance, max(balance * min_pct / 100, 200))
        balance -= payment
        months += 1
    return months, paid_interest


def exclusion(fields: ClauseFields, ctx: LoanContext, pos: int, text: str) -> RupeeImpact:
    lower = text.lower()
    dur = _nearest(fields.durations, pos)
    pct = _nearest(fields.percents, pos)
    if "co-pay" in lower or "copay" in lower or "co pay" in lower:
        if pct:
            example = 300_000
            share = example * pct.value / 100
            return RupeeImpact(headline=f"You pay {inr(share)} of a {inr(example)} hospital bill", amount=round(share, 2), basis=f"{pct.value:g}% co-payment on every claim, shown on an example bill of {inr(example)}.")
    if dur and "wait" in lower:
        return RupeeImpact(headline=f"No payout for these conditions for the first {dur.raw}", amount=None, basis="Waiting period stated in the clause.")
    if pct and ("room" in lower or "sub-limit" in lower or "sublimit" in lower):
        return RupeeImpact(headline=f"Payout limited to {pct.value:g}% for this item", amount=None, basis="Sub-limit stated in the clause. Costs above it are yours to pay.")
    return _no_figure("Some claims will not be paid, or only partly. Read the list before you need it.")


def no_rupee(message: str):
    def fn(fields: ClauseFields, ctx: LoanContext, pos: int, text: str) -> RupeeImpact:
        return _no_figure(message)

    return fn


CALCULATORS = {
    "prepayment_penalty": prepayment,
    "floating_rate": floating,
    "late_payment": late_payment,
    "bounce_charge": bounce,
    "processing_fee": processing,
    "auto_renewal": auto_renewal,
    "deferred_interest": deferred_interest,
    "bundled_insurance": bundled_insurance,
    "recurring_fee": recurring,
    "minimum_due": minimum_due,
    "insurance_exclusion": exclusion,
    "unilateral_change": no_rupee("No fixed rupee cost. Fees or rates can be raised later, so today's numbers may not hold."),
    "set_off_lien": no_rupee("No fixed rupee cost. Money in your other accounts with this lender can be used to clear dues."),
    "data_sharing": no_rupee("No direct rupee cost. Your details may reach other companies and marketers."),
}


def compute(category: str, fields: ClauseFields, ctx: LoanContext, cue_pos: int, clause_text: str) -> RupeeImpact:
    fn = CALCULATORS.get(category)
    if fn is None:
        return _no_figure("No rupee estimate for this item.")
    try:
        return fn(fields, ctx, cue_pos, clause_text)
    except Exception:
        return _no_figure("Could not estimate this in rupees. Check the numbers above.")


def all_numbers(impact: RupeeImpact | None, fields: ClauseFields, ctx: LoanContext) -> set[str]:
    """Every number the explainer is allowed to mention (used by the number guard)."""
    allowed: set[str] = set()
    texts = []
    if impact:
        texts += [impact.headline, impact.basis, *impact.assumptions]
    for m in fields.amounts:
        allowed.add(_digits(m.value))
    for p in fields.percents:
        allowed.add(_digits(p.value))
    for d in fields.durations:
        allowed.add(_digits(d.months))
        allowed.update(re.findall(r"\d+(?:\.\d+)?", d.raw))
    for v in (ctx.principal, ctx.annual_rate, ctx.tenure_months, ctx.emi):
        if v is not None:
            allowed.add(_digits(v))
    for t in texts:
        for n in re.findall(r"\d[\d,]*(?:\.\d+)?", t):
            allowed.add(_digits(float(n.replace(",", ""))))
    return allowed


def _digits(v: float) -> str:
    return f"{round(float(v), 2):g}"


