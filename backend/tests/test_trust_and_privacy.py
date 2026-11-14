"""The 'intelligence' features: PII detection, document typing, answer verification, calendar export."""
from datetime import datetime, timezone

import pytest

from app.services import calendar_ics, doctype, llm, pii, verify
from conftest import upload


def aadhaar(payload="23456789012"):
    return payload + pii.verhoeff_check_digit(payload)


# ------------------------------------------------------------------ PII
def test_verhoeff_matches_the_published_example():
    assert pii.verhoeff_check_digit("236") == "3"  # Wikipedia's worked example
    assert pii.verhoeff_valid("2363") and not pii.verhoeff_valid("2364")


def test_aadhaar_is_found_masked_and_checksum_gated():
    good = aadhaar()
    text = f"Aadhaar: {good[:4]} {good[4:8]} {good[8:]} and order no 234567890123."
    hits = pii.find_pii(text)
    assert [h.kind for h in hits] == ["aadhaar"]  # the random 12 digits fail the checksum
    assert hits[0].masked == f"XXXX XXXX {good[-4:]}"
    assert good not in pii.redact(text).replace(" ", "")


def test_other_identifiers_and_masking():
    text = "PAN ABCPE1234F, mobile +91 98765 43210, mail ganga@example.com, IFSC SBIN0001234, GSTIN 33ABCPE1234F1Z5."
    kinds = {h.kind for h in pii.find_pii(text)}
    assert kinds == {"pan", "phone", "email", "ifsc", "gstin"}
    red = pii.redact(text)
    for secret in ("ABCPE1234F", "98765 43210", "ganga@example.com", "SBIN0001234"):
        assert secret not in red
    assert "g****@example.com" in red and "XXXXXX3210" in red


def test_plain_numbers_are_not_pii():
    assert pii.find_pii("Sum insured Rs. 5,00,000 premium 14850 policy 123456789012") == []


# ------------------------------------------------------------------ document type
def test_classifies_documents_and_explains_why():
    ins = doctype.classify("Policy period 2026. Sum insured Rs 5,00,000. Waiting period for claims; premium payable.", "p.txt")
    assert ins.key == "insurance_policy" and "sum insured" in ins.matched
    rent = doctype.classify("The tenant pays monthly rent to the landlord. Security deposit is refundable.")
    assert rent.key == "rental_agreement"
    assert doctype.classify("hello world").key == "other"


def test_checklist_reports_missing_clauses():
    items = {c["item"]: c["found"] for c in doctype.checklist("insurance_policy", "Sum insured and premium only.")}
    assert items["Sum insured"] and items["Premium"]
    assert not items["Waiting period"] and not items["Exclusions"]
    assert doctype.checklist("other", "x") == []


# ------------------------------------------------------------------ answer verification
SOURCE = ["Waiting period for pre-existing diseases is 24 months. Sum insured is Rs. 5,00,000. Policy ends on 14 March 2027."]


def test_verified_when_every_figure_is_in_the_sources():
    r = verify.verify_answer("The waiting period is 24 months and the cover is Rs 500000, valid till 14/03/2027.", SOURCE)
    assert r["verdict"] == "VERIFIED" and r["supported"] == r["total"] >= 3


def test_wrong_figure_is_flagged():
    r = verify.verify_answer("The waiting period is 48 months.", SOURCE)
    assert r["verdict"] == "UNVERIFIED"
    assert r["claims"][0] == {"kind": "number", "text": "48", "supported": False}


def test_partial_and_no_figures():
    assert verify.verify_answer("24 months, premium 99999.", SOURCE)["verdict"] == "PARTIAL"
    assert verify.verify_answer("It is covered.", SOURCE)["verdict"] == "NO_FIGURES"


def test_dates_compare_by_value_not_by_format_and_list_markers_are_ignored():
    assert verify.verify_answer("It ends 2027-03-14.", SOURCE)["verdict"] == "VERIFIED"
    assert verify.verify_answer("1. Covered.\n2. Waiting period 24 months.", SOURCE)["verdict"] == "VERIFIED"
    assert verify.verify_answer("It ends on 15 March 2027.", SOURCE)["verdict"] == "UNVERIFIED"


# ------------------------------------------------------------------ calendar
def test_ics_is_valid_stable_and_escaped():
    alert = {"id": 7, "title": "Expires, soon", "description": "a;b\nline", "deadline": "2027-03-14", "filename": "p" * 90 + ".txt"}
    out = calendar_ics.build_ics([alert], now=datetime(2026, 11, 14, tzinfo=timezone.utc))
    assert out.startswith("BEGIN:VCALENDAR\r\n") and out.endswith("END:VCALENDAR\r\n")
    assert "UID:doclock-alert-7@doclock.local" in out and "DTSTART;VALUE=DATE:20270314" in out and "DTEND;VALUE=DATE:20270315" in out
    assert "Expires\\, soon" in out and r"a\;b\nline" in out
    assert all(len(line.encode()) <= 75 for line in out.split("\r\n"))
    assert out.count("BEGIN:VALARM") == 2


# ------------------------------------------------------------------ through the API
def test_api_insights_redaction_privacy_and_calendar(client, auth):
    good = aadhaar()
    text = (f"Health policy. Policy period: 15 March 2026 to 14 March 2027. Sum insured Rs. 5,00,000. Premium Rs. 14,850. "
            f"Waiting period 24 months. Insured Aadhaar {good}. Mobile 9876543210.")
    doc = upload(client, auth, "policy.txt", text).json()
    detail = client.get(f"/api/documents/{doc['id']}", headers=auth).json()
    assert detail["status"] == "PROCESSED" and detail["category"] == "insurance_policy"

    ins = client.get(f"/api/documents/{doc['id']}/insights", headers=auth).json()
    assert ins["type"] == "insurance_policy" and ins["pii"]["counts"] == {"aadhaar": 1, "phone": 1}
    assert good not in str(ins)  # the API never returns raw identifiers
    assert any(c["item"] == "Exclusions" and not c["found"] for c in ins["checklist"])

    red = client.get(f"/api/documents/{doc['id']}/redacted", headers=auth).json()["text"]
    assert good not in red and "9876543210" not in red and "Sum insured" in red

    rep = client.get("/api/privacy", headers=auth).json()
    assert rep["documentsScanned"] == 1 and rep["documentsWithPii"] == 1 and rep["totals"]["aadhaar"] == 1

    ics = client.get("/api/alerts/calendar.ics", headers=auth)
    assert ics.headers["content-type"].startswith("text/calendar") and "BEGIN:VEVENT" in ics.text
    assert client.get("/api/alerts/calendar.ics").status_code == 401
    assert client.get("/api/privacy").status_code == 401


def test_chat_returns_and_persists_verification(client, auth, monkeypatch):
    upload(client, auth, "p.txt", "Waiting period for pre-existing diseases is 24 months of continuous coverage.")
    monkeypatch.setattr(llm, "generate_answer", lambda *a: "The waiting period is 48 months.")
    r = client.post("/api/chat", headers=auth, json={"message": "waiting period pre-existing diseases"}).json()
    assert r["verification"]["verdict"] == "UNVERIFIED"
    msgs = client.get(f"/api/chat/conversations/{r['conversationId']}/messages", headers=auth).json()
    assert msgs[-1]["verification"]["verdict"] == "UNVERIFIED" and msgs[-1]["citations"]
