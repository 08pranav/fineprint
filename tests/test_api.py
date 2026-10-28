from fastapi.testclient import TestClient

from fineprint.api import app

from conftest import sample

client = TestClient(app)
DOC = sample("s01_personal_loan.txt")


def test_health_reports_rules_mode():
    r = client.get("/api/health").json()
    assert r["status"] == "ok" and r["mode"] == "rules"


def test_index_page_is_served():
    r = client.get("/")
    assert r.status_code == 200 and "FinePrint" in r.text


def test_samples_list_and_fetch():
    items = client.get("/api/samples").json()
    assert len(items) == 12
    s = client.get(f"/api/samples/{items[0]['id']}").json()
    assert "Processing fee" in s["text"]
    assert client.get("/api/samples/nope").status_code == 404


def test_extract_masks_and_counts():
    r = client.post("/api/extract", data={"text": DOC}).json()
    assert r["clause_count"] > 10 and r["pii_masked"]["pan"] == 1
    assert "BQRXD4821K" not in r["text"]
    assert r["context"]["principal"] == 300000


def test_extract_rejects_short_text_and_bad_files():
    r = client.post("/api/extract", data={"text": "too short"})
    assert r.status_code == 400 and "too short" in r.json()["detail"]
    r = client.post("/api/extract", files={"file": ("photo.jpg", b"\xff\xd8\xff", "image/jpeg")})
    assert r.status_code == 400 and "PDF" in r.json()["detail"]
    r = client.post("/api/extract", files={"file": ("broken.pdf", b"%PDF-1.4 not really", "application/pdf")})
    assert r.status_code == 400


def test_extract_reads_text_file_upload():
    r = client.post("/api/extract", files={"file": ("terms.txt", DOC.encode(), "text/plain")})
    assert r.status_code == 200 and r.json()["clause_count"] > 10


def test_analyze_recalculate_explain_ask_flow():
    text = client.post("/api/extract", data={"text": DOC}).json()["text"]
    a = client.post("/api/analyze", json={"text": text, "level": "simple"}).json()
    assert a["method"] == "rules" and a["summary"]["high"] >= 5
    assert all(f["quote"] and f["explanation"] for f in a["flags"])

    ctx = dict(a["context"], principal=600000)
    rc = client.post("/api/recalculate", json={"text": text, "context": ctx, "flags": a["flags"], "level": "simple"}).json()
    fee_before = next(f for f in a["flags"] if f["category"] == "processing_fee")["impact"]["amount"]
    fee_after = next(f for f in rc["flags"] if f["category"] == "processing_fee")["impact"]["amount"]
    assert fee_after == 2 * fee_before

    ex = client.post("/api/explain", json={"context": a["context"], "flags": a["flags"], "level": "expert", "language": "en"}).json()
    assert ex["flags"][0]["explanation"] != a["flags"][0]["explanation"]

    ask = client.post("/api/ask", json={"question": "mera EMI bounce hua toh kitna lagega?", "text": text}).json()
    assert ask["detected_language"] == "hinglish" and ask["cited_clauses"]


def test_ask_validates_question():
    assert client.post("/api/ask", json={"question": "?", "text": DOC}).status_code == 400
