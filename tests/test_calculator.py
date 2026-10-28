import pytest

from fineprint.calc.impact import _simulate_minimum, compute, emi
from fineprint.extract.money import extract_fields
from fineprint.schemas import LoanContext

CTX = LoanContext(principal=300000, annual_rate=16, tenure_months=36)


def test_emi_formula_matches_known_value():
    assert emi(100000, 12, 12) == pytest.approx(8884.88, abs=0.01)
    assert emi(120000, 0, 12) == 10000


def test_late_fee_monthly_percent_on_emi():
    text = "Any delay in payment of EMI shall attract penal charges of 2% per month on the overdue EMI amount."
    impact = compute("late_payment", extract_fields(text), CTX, 20, text)
    assert impact.amount == pytest.approx(emi(300000, 16, 36) * 0.02, abs=0.01)
    assert "each month" in impact.headline


def test_annual_penal_rate_is_converted_to_monthly():
    text = "Overdue EMIs will attract penal charges at 24% per annum on the overdue amount."
    impact = compute("late_payment", extract_fields(text), CTX, 0, text)
    assert impact.amount == pytest.approx(emi(300000, 16, 36) * 0.02, abs=0.01)


def test_bounce_fee_adds_gst_when_clause_says_so():
    text = "A bounce charge of ₹500 plus applicable GST will be levied for each instance."
    impact = compute("bounce_charge", extract_fields(text), CTX, 0, text)
    assert impact.amount == 590


def test_processing_fee_respects_minimum():
    text = "Processing fee of 1% of the loan amount, subject to a minimum of ₹5,000."
    impact = compute("processing_fee", extract_fields(text), LoanContext(principal=200000), 0, text)
    assert impact.amount == 5000


def test_floating_rate_one_point_rise():
    impact = compute("floating_rate", extract_fields("floating rate"), CTX, 0, "floating rate")
    expected = (emi(300000, 17, 36) - emi(300000, 16, 36)) * 36
    assert impact.amount == pytest.approx(expected, abs=0.5)


def test_minimum_due_takes_years_and_costs_interest():
    months, interest = _simulate_minimum(50000, 3.75, 5)
    assert months > 60 and interest > 50000


def test_missing_numbers_give_no_figure_not_a_guess():
    impact = compute("prepayment_penalty", extract_fields("Foreclosure charges apply."), LoanContext(), 0, "Foreclosure charges apply.")
    assert impact.amount is None and "Ask" in impact.headline


def test_unknown_category_is_safe():
    assert compute("nonsense", extract_fields(""), CTX, 0, "").amount is None
