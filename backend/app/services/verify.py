"""Answer verification: does every number and date in the model's answer appear in the passages it was given?

A small local model can state "24 months" when the source says "48 months". This check is deterministic
(no second LLM call): it pulls figures and dates out of the *answer* and looks for each one in the *retrieved
text*. Figures that cannot be found are flagged in the UI so the user knows to check the original.

It verifies numbers and dates, not meaning: a correct figure used for the wrong thing still passes.
"""
from __future__ import annotations

import re

from app.services import facts

_NUMBER = re.compile(r"(?<![\w/.-])(\d[\d,]*(?:\.\d+)?)(?![\w/-]*\d)")
_LIST_MARKER = re.compile(r"^\s*\d{1,2}[.)]\s", re.M)
_WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                 "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "sixty": 60, "ninety": 90}
_WORD_RE = re.compile(r"\b(" + "|".join(_WORD_NUMBERS) + r")\b", re.I)


def _canon(raw: str) -> str:
    """'5,00,000' / '500000.00' -> '500000'."""
    value = raw.replace(",", "")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return value.lstrip("0") or "0"


def _dates(text: str) -> set:
    return {h.value for h in facts.find_dates(text)}


def _numbers(text: str, strip_dates: bool = True) -> set[str]:
    if strip_dates:  # blank out date spans so '15 March 2026' does not contribute 15 and 2026
        for h in sorted(facts.find_dates(text), key=lambda h: -h.start):
            text = text[:h.start] + " " * (h.end - h.start) + text[h.end:]
    text = _LIST_MARKER.sub(" ", text)
    found = {_canon(m.group(1)) for m in _NUMBER.finditer(text)}
    found |= {str(_WORD_NUMBERS[m.group(1).lower()]) for m in _WORD_RE.finditer(text)}
    return found


def verify_answer(answer: str, passages: list[str]) -> dict:
    """Return {verdict, supported, total, claims:[{kind, text, supported}]}.

    verdict: VERIFIED (all figures found), PARTIAL, UNVERIFIED (none found), NO_FIGURES (nothing to check).
    """
    source = "\n".join(passages)
    source_dates, source_numbers = _dates(source), _numbers(source)
    claims: list[dict] = []

    for hit in facts.find_dates(answer):
        claims.append({"kind": "date", "text": answer[hit.start:hit.end], "supported": hit.value in source_dates})
    for number in sorted(_numbers(answer)):
        claims.append({"kind": "number", "text": number, "supported": number in source_numbers})

    total = len(claims)
    supported = sum(1 for c in claims if c["supported"])
    if total == 0:
        verdict = "NO_FIGURES"
    elif supported == total:
        verdict = "VERIFIED"
    elif supported == 0:
        verdict = "UNVERIFIED"
    else:
        verdict = "PARTIAL"
    return {"verdict": verdict, "supported": supported, "total": total, "claims": claims}
