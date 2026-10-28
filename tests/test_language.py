import json

from fineprint.explain.explainer import explain, numbers_ok
from fineprint.explain.readability import flesch
from fineprint.ingest.segmenter import segment
from fineprint.qa.chat import answer, unsupported_numbers
from fineprint.qa.guardrails import is_advice_request
from fineprint.qa.lang import detect_language
from fineprint.risk.pipeline import detect
from fineprint.schemas import LoanContext

from conftest import FakeLLM, sample

DOC = sample("s01_personal_loan.txt")


def test_language_detection():
    assert detect_language("mera EMI bounce hua toh kitna lagega?") == "hinglish"
    assert detect_language("What happens if I pay late?") == "en"
    assert detect_language("मेरी किस्त देर से गई तो कितना लगेगा?") == "hi"
    assert detect_language("माझा हप्ता उशिरा भरला तर किती दंड लागेल?") == "mr"


def test_hinglish_question_retrieves_the_bounce_clause_offline():
    r = answer("mera EMI bounce hua toh kitna lagega?", DOC, llm=None)
    assert r.detected_language == "hinglish" and not r.abstained
    assert "bounce charge" in r.answer and "₹590" in r.answer
    assert r.answer.startswith("Aapke document")


def test_marathi_question_retrieves_late_fee_clause():
    r = answer("माझा हप्ता उशिरा भरला तर किती दंड लागेल?", DOC, llm=None)
    assert r.detected_language == "mr" and "penal charges" in r.answer


def test_unrelated_question_abstains():
    r = answer("What is the capital of France?", DOC, llm=None)
    assert r.abstained and not r.cited_clauses


def test_advice_guardrail():
    assert is_advice_request("Should I take this loan?")
    assert is_advice_request("kya mujhe yeh loan lena chahiye?")
    assert not is_advice_request("What is the foreclosure charge?")
    r = answer("Should I take this loan given the foreclosure charges?", DOC, llm=None)
    assert r.advice_guardrail and "cannot tell you whether" in r.answer


def test_model_answer_with_invented_citation_or_number_falls_back():
    r = answer("What is the bounce charge?", DOC, llm=FakeLLM("The bounce charge is ₹900 [C14]."))
    assert not r.model_used and "₹590" in r.answer  # ₹900 is not in the clause
    r = answer("What is the bounce charge?", DOC, llm=FakeLLM("It is ₹500 plus GST [C99]."))
    assert not r.model_used  # C99 does not exist, so nothing valid is cited


def test_model_answer_with_valid_citation_is_used():
    r = answer("What is the bounce charge?", DOC, llm=FakeLLM("It is ₹500 plus GST per bounce [C14]."))
    assert r.model_used and r.cited_clauses == ["C14"]


def test_unsupported_numbers_ignores_citation_ids():
    assert unsupported_numbers("Charge is ₹500 [C14].", {"500"}) == []
    assert unsupported_numbers("Charge is ₹700 [C14].", {"500"}) == ["700"]


def test_number_guard_rejects_invented_numbers():
    assert numbers_ok("You pay ₹590 each time.", {"590", "500"})
    assert not numbers_ok("You pay ₹950 each time.", {"590", "500"})
    assert numbers_ok("तुम्हाला ₹५९० भरावे लागतील.", {"590"})  # Devanagari digits are checked too


def test_model_explanations_pass_guard_or_fall_back():
    clauses = segment("1. A bounce charge of ₹500 plus applicable GST will be levied for each dishonoured NACH mandate.\n"
                      "2. Penal charges of 2% per month apply on the overdue EMI.")
    ctx = LoanContext(emi=10000)
    flags, _ = detect(clauses, ctx, method="rules")
    good = {f.id: f"Each bounce costs {f.impact.headline.split()[0]}." for f in flags}
    bad_id = flags[0].id
    reply = json.dumps({"explanations": [{"id": i, "text": (t if i != bad_id else "It costs ₹12,345.")} for i, t in good.items()]})
    warnings = explain(flags, ctx, level="simple", language="en", llm=FakeLLM(reply))
    sources = {f.id: f.explanation_source for f in flags}
    assert sources[bad_id] == "template" and list(sources.values()).count("model") == len(flags) - 1
    assert any("number that is not in the document" in w for w in warnings)


def test_offline_non_english_explains_in_english_with_notice():
    flags, _ = detect(segment("1. A bounce charge of ₹500 will be levied."), LoanContext(), method="rules")
    warnings = explain(flags, LoanContext(), level="standard", language="hi", llm=None)
    assert flags[0].explanation and any("Showing English" in w for w in warnings)


def test_readability_orders_simple_text_above_complex():
    simple = "You pay more if you are late. The fee is small but it adds up."
    hard = "Penal charges accrue on overdue instalments notwithstanding contractual amortisation obligations."
    assert flesch(simple) > flesch(hard)
