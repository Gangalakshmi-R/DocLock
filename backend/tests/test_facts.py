import json
from datetime import date

import pytest

from app import config
from app.services import facts, llm

D = date


def dates_in(text):
    return [h.value for h in facts.find_dates(text)]


# ---------------------------------------------------------------- date recognition
@pytest.mark.parametrize("text,expected", [
    ("Valid until 2026-12-31.", [D(2026, 12, 31)]),
    ("Pay by 31/12/2026", [D(2026, 12, 31)]),
    ("Pay by 31-12-2026", [D(2026, 12, 31)]),
    ("Pay by 31.12.2026", [D(2026, 12, 31)]),
    ("on 31 December 2026", [D(2026, 12, 31)]),
    ("on 1st Mar 2027", [D(2027, 3, 1)]),
    ("on 22nd Sept, 2026", [D(2026, 9, 22)]),
    ("on December 31, 2026", [D(2026, 12, 31)]),
    ("on Jan. 5th 2027", [D(2027, 1, 5)]),
])
def test_recognises_common_date_formats(text, expected):
    assert dates_in(text) == expected


def test_numeric_dates_are_day_first_by_default_and_tolerate_us_order():
    assert config.DATES_DAY_FIRST is True
    assert dates_in("03/04/2026") == [D(2026, 4, 3)]      # 3 April
    assert dates_in("12/25/2026") == [D(2026, 12, 25)]    # impossible as day-first -> falls back to month-first


@pytest.mark.parametrize("text", ["31/02/2026", "01/01/1850", "13/13/2026", "version 2.3.4", "call 044-2345-6789", "no dates here"])
def test_ignores_invalid_or_implausible_dates(text):
    assert dates_in(text) == []


def test_finds_several_dates_in_order_without_double_counting():
    assert dates_in("Start 15 March 2026, end 14 March 2027, review 2027-01-10") == [D(2026, 3, 15), D(2027, 3, 14), D(2027, 1, 10)]


# ---------------------------------------------------------------- labelling dates
def extract(text):
    return {(f.key_name, f.value, f.deadline_kind) for f in facts.extract_date_facts(text)}


def test_expiry_date_with_label():
    assert ("policy_expiry_date", "2027-03-14", "EXPIRY") in extract("Policy expiry date: 14 March 2027")


def test_deadline_and_due_and_renewal_kinds():
    text = ("Scholarship application deadline: 31 August 2026\n"
            "Last date to pay without fine: 20 August 2026\n"
            "Rent due on 5 July 2026\n"
            "Renewal date: 1 June 2027")
    kinds = {f.value: f.deadline_kind for f in facts.extract_date_facts(text)}
    assert kinds == {"2026-08-31": "DEADLINE", "2026-08-20": "DEADLINE", "2026-07-05": "DUE", "2027-06-01": "RENEWAL"}


def test_closest_keyword_wins():
    # 'renewal' appears earlier in the sentence than 'due'; the date belongs to 'due'.
    f = facts.extract_date_facts("Renewal reminders are sent early, payment due 10 May 2027")[0]
    assert f.deadline_kind == "DUE"


def test_end_of_a_date_range_is_an_expiry():
    found = {f.value: f for f in facts.extract_date_facts("Lease period: 1 June 2026 to 30 April 2027.")}
    assert found["2026-06-01"].deadline_kind is None
    assert found["2027-04-30"].deadline_kind == "EXPIRY"
    assert found["2027-04-30"].key_name == "expiry_date"


def test_dates_without_context_are_stored_but_never_become_alerts():
    fs = facts.extract_date_facts("The building was completed on 12 January 2020.")
    assert fs and fs[0].deadline is None
    assert facts.alerts_from_facts(fs, today=D(2026, 1, 1)) == []


def test_plain_dates_are_capped():
    text = "\n".join(f"Meeting on {i + 1} March 2026" for i in range(25))
    assert len(facts.extract_date_facts(text)) == facts.MAX_PLAIN_DATES


# ---------------------------------------------------------------- amounts
def amounts(text):
    return {(f.key_name, f.value) for f in facts.extract_amount_facts(text)}


def test_amounts_in_several_currency_styles():
    text = "Annual premium: ₹14,850\nSum insured Rs. 5,00,000\nFee $1,200.50\nDeposit 55000 INR\nPenalty USD 25"
    got = amounts(text)
    assert ("annual_premium", "₹14,850") in got
    assert any(v == "Rs. 5,00,000" for _, v in got)
    assert any(v == "$1,200.50" for _, v in got)
    assert any(v == "55000 INR" for _, v in got)
    assert any(v == "USD 25" for _, v in got)


def test_amount_regex_does_not_fire_on_ordinary_words_or_numbers():
    assert amounts("Hours 5 and versus 7, room 12, 3 floors") == set()


# ---------------------------------------------------------------- LLM output is validated, never trusted
DOC = "Policy expiry date: 14 March 2027. Annual premium: ₹14,850. Insurer: Sunrise Health Assurance."


def test_llm_facts_grounded_in_the_text_are_kept():
    raw = json.dumps({"facts": [
        {"type": "ORGANIZATION", "name": "insurer", "value": "Sunrise Health Assurance", "deadline": None, "deadline_kind": None},
        {"type": "DATE", "name": "policy_end", "value": "14 March 2027", "deadline": "2027-03-14", "deadline_kind": "EXPIRY"},
    ]})
    got = facts.parse_llm_facts(raw, DOC)
    assert [(f.key_name, f.deadline_kind) for f in got] == [("insurer", None), ("policy_end", "EXPIRY")]
    assert got[1].deadline == D(2027, 3, 14) and got[1].value == "2027-03-14"


def test_llm_hallucinated_values_and_dates_are_dropped():
    raw = json.dumps({"facts": [
        {"type": "ORGANIZATION", "name": "insurer", "value": "Totally Different Corp"},                 # not in text
        {"type": "DATE", "name": "end", "value": "2031-01-01", "deadline": "2031-01-01", "deadline_kind": "EXPIRY"},  # date not in text
        {"type": "AMOUNT", "name": "premium", "value": "₹14,850"},                                        # grounded
    ]})
    got = facts.parse_llm_facts(raw, DOC)
    assert [f.key_name for f in got] == ["premium"]


def test_llm_defaults_and_normalisation():
    raw = json.dumps([{"type": "weird", "name": "Some Odd Name!", "value": "Sunrise Health Assurance"},
                      {"type": "DATE", "value": "x", "deadline": "2027-03-14", "deadline_kind": "nonsense"}])
    a, b = facts.parse_llm_facts(raw, DOC)
    assert (a.fact_type, a.key_name) == ("OTHER", "some_odd_name")
    assert (b.deadline, b.deadline_kind) == (D(2027, 3, 14), "DEADLINE")


@pytest.mark.parametrize("raw", ["", "not json", "null", "42", '{"facts": "oops"}', '{"facts": [1, "a", null]}', None])
def test_malformed_llm_output_yields_nothing(raw):
    assert facts.parse_llm_facts(raw, DOC) == []


def test_merge_does_not_duplicate_values_or_deadlines():
    regex = [facts.ExtractedFact("DATE", "policy_expiry_date", "2027-03-14", D(2027, 3, 14), "EXPIRY")]
    llm_side = [facts.ExtractedFact("DATE", "end", "2027-03-14", D(2027, 3, 14), "DEADLINE"),   # same date
                facts.ExtractedFact("PERSON", "holder", "Priya Raman")]
    merged = facts.merge_facts(regex, llm_side)
    assert [f.key_name for f in merged] == ["policy_expiry_date", "holder"]


def test_extract_facts_survives_llm_failure(monkeypatch):
    def boom(_):
        raise RuntimeError("ollama down")
    monkeypatch.setattr(llm, "request_fact_json", boom)
    got = facts.extract_facts(DOC, use_llm=True)
    assert any(f.deadline_kind == "EXPIRY" for f in got)  # regex facts are still returned


def test_extract_facts_merges_llm_results(monkeypatch):
    monkeypatch.setattr(llm, "request_fact_json", lambda _: json.dumps(
        {"facts": [{"type": "ORGANIZATION", "name": "insurer", "value": "Sunrise Health Assurance"}]}))
    names = {f.key_name for f in facts.extract_facts(DOC, use_llm=True)}
    assert {"insurer", "policy_expiry_date", "annual_premium"} <= names


def test_llm_not_called_when_disabled(monkeypatch):
    monkeypatch.setattr(llm, "request_fact_json", lambda _: pytest.fail("LLM must not be called"))
    facts.extract_facts(DOC, use_llm=False)


# ---------------------------------------------------------------- alerts
def test_alerts_are_sorted_deduplicated_and_skip_stale_dates():
    today = D(2026, 11, 12)
    fs = [
        facts.ExtractedFact("DATE", "policy_expiry_date", "2027-03-14", D(2027, 3, 14), "EXPIRY", "Policy expiry date: 14 March 2027"),
        facts.ExtractedFact("DATE", "scholarship_deadline", "2026-12-01", D(2026, 12, 1), "DEADLINE"),
        facts.ExtractedFact("DATE", "dup", "2026-12-01", D(2026, 12, 1), "DEADLINE"),                   # duplicate of the above
        facts.ExtractedFact("DATE", "ancient_expiry", "2019-01-01", D(2019, 1, 1), "EXPIRY"),           # > 1 year old
        facts.ExtractedFact("DATE", "overdue_fee", "2026-10-30", D(2026, 10, 30), "DUE"),               # recently overdue -> kept
    ]
    alerts = facts.alerts_from_facts(fs, today=today)
    assert [a["deadline_date"] for a in alerts] == [D(2026, 10, 30), D(2026, 12, 1), D(2027, 3, 14)]
    assert alerts[2]["title"] == "Policy expiry date"
    assert alerts[2]["description"] == "Policy expiry date: 14 March 2027"


def test_generic_labels_get_a_readable_title():
    f = facts.ExtractedFact("DATE", "expiry_date", "2027-04-30", D(2027, 4, 30), "EXPIRY")
    assert facts.alerts_from_facts([f], today=D(2026, 11, 12))[0]["title"] == "Expires"
