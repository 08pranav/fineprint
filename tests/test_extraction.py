from fineprint.extract.context import detect_doc_type, extract_context
from fineprint.extract.money import extract_fields, find_durations, find_money, find_percents, inr
from fineprint.ingest.pii import mask_pii
from fineprint.ingest.segmenter import segment

from conftest import sample


def test_indian_money_formats():
    text = "₹3,00,000 or Rs. 1.5 lakh or INR 2,00,000 or Rs.500/- or ₹50k or 2 crore"
    assert [m.value for m in find_money(text)] == [300000, 150000, 200000, 500, 50000, 20000000]


def test_percent_periods():
    got = [(p.value, p.period) for p in find_percents("2% p.m., 24% per annum, 3.5 per cent monthly, 5%")]
    assert got == [(2, "month"), (24, "year"), (3.5, "month"), (5, "unspecified")]


def test_durations_in_months():
    assert [d.months for d in find_durations("36 months, three years, 2 yrs")] == [36, 36, 24]


def test_gst_detection():
    assert extract_fields("₹500 plus applicable GST").plus_gst
    assert not extract_fields("₹500 inclusive of all taxes").plus_gst


def test_inr_uses_indian_grouping():
    assert inr(1234567) == "₹12,34,567"
    assert inr(590) == "₹590"
    assert inr(100000) == "₹1,00,000"


def test_pii_is_masked_but_amounts_are_not():
    text = "Applicant: Rohan Deshmukh\nPAN: BQRXD4821K, Aadhaar 4821 6630 1295, call +91 91234 56789, card 4111 1111 1111 1111, A/c No: 0000123456, amount ₹1,50,000, x@example.com"
    masked, counts = mask_pii(text)
    for secret in ("Rohan", "BQRXD4821K", "4821 6630", "91234", "4111", "0000123456", "x@example.com"):
        assert secret not in masked
    assert "₹1,50,000" in masked
    assert counts == {"name": 1, "email": 1, "card": 1, "aadhaar": 1, "pan": 1, "account": 1, "phone": 1}


def test_money_after_insured_label_is_not_a_name():
    masked, counts = mask_pii("Sum insured: Rs. 10,00,000")
    assert masked == "Sum insured: Rs. 10,00,000" and not counts


def test_segmenter_keeps_offsets_and_headings():
    text, _ = mask_pii(sample("s01_personal_loan.txt"))
    clauses = segment(text)
    fee = next(c for c in clauses if c.text.startswith("5. Processing fee"))
    assert fee.heading == "Fees and Charges"
    assert " ".join(text[fee.start: fee.end].split()) == fee.text
    assert [c.number for c in clauses] == list(range(1, len(clauses) + 1))


def test_long_paragraph_is_split_at_sentences():
    para = " ".join(f"Sentence number {i} explains a charge of Rs. {i}00 in some detail." for i in range(30))
    clauses = segment(para)
    assert len(clauses) > 1 and all(len(c.text) <= 560 for c in clauses)


def test_context_prefill_from_sample():
    text, _ = mask_pii(sample("s01_personal_loan.txt"))
    ctx = extract_context(segment(text), text)
    assert (ctx.principal, ctx.annual_rate, ctx.tenure_months, ctx.emi) == (300000, 16, 36, 10547)


def test_doc_type_detection():
    assert detect_doc_type(sample("s03_credit_card.txt")) == "credit_card"
    assert detect_doc_type(sample("s05_health_insurance.txt")) == "insurance"
    assert detect_doc_type(sample("s04_no_cost_emi.txt")) == "bnpl"
