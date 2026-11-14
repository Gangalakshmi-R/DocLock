"""Detect Indian personal identifiers in document text and mask them.

Nothing here is stored: findings are computed on demand from the extracted text and only ever returned in
*masked* form (e.g. ``XXXX XXXX 9012``), so the privacy report itself never leaks the identifiers.

Aadhaar numbers are validated with the Verhoeff checksum, so random 12-digit numbers (phone + digits, order
numbers) are not flagged. PAN, GSTIN and IFSC are matched by their published structure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_D = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
      [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
      [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
      [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_P = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
      [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
      [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]
_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_valid(number: str) -> bool:
    """True when the digit string (check digit included) passes the Verhoeff checksum."""
    if not number.isdigit():
        return False
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_check_digit(payload: str) -> str:
    """Check digit to append to ``payload`` (used by tests and the sample-data generator)."""
    c = 0
    for i, ch in enumerate(reversed(payload)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str(_INV[c])


KINDS = {
    "aadhaar": "Aadhaar number", "pan": "PAN", "gstin": "GSTIN", "ifsc": "IFSC code",
    "phone": "Mobile number", "email": "Email address",
}

_AADHAAR = re.compile(r"(?<![\d-])([2-9]\d{3})[ -]?(\d{4})[ -]?(\d{4})(?![\d-])")
_PAN = re.compile(r"\b[A-Z]{3}[ABCFGHLJPT][A-Z]\d{4}[A-Z]\b")
_GSTIN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
_IFSC = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
_PHONE = re.compile(r"(?<![\d-])(?:\+91[ -]?|0)?([6-9]\d{4})[ -]?(\d{5})(?![\d-])")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")


@dataclass(frozen=True)
class PiiHit:
    kind: str
    start: int
    end: int
    masked: str


def _keep_last(value: str, keep: int = 4, mask: str = "X") -> str:
    out, seen = [], 0
    for ch in reversed(value):
        if ch.isalnum():
            out.append(ch if seen < keep else mask)
            seen += 1
        else:
            out.append(ch)
    return "".join(reversed(out))


def _mask_email(value: str) -> str:
    local, _, domain = value.partition("@")
    return f"{local[:1]}{'*' * max(len(local) - 1, 1)}@{domain}"


def find_pii(text: str) -> list[PiiHit]:
    """All identifiers found in ``text``, non-overlapping, in document order. Values come back masked."""
    hits: list[PiiHit] = []

    def add(kind: str, m: re.Match, masked: str) -> None:
        hits.append(PiiHit(kind, m.start(), m.end(), masked))

    for m in _AADHAAR.finditer(text):
        digits = "".join(m.groups())
        if verhoeff_valid(digits):
            add("aadhaar", m, f"XXXX XXXX {digits[-4:]}")
    for m in _PAN.finditer(text):
        add("pan", m, _keep_last(m.group(), 4))
    for m in _GSTIN.finditer(text):
        add("gstin", m, _keep_last(m.group(), 4))
    for m in _IFSC.finditer(text):
        add("ifsc", m, m.group()[:4] + "0******")
    for m in _EMAIL.finditer(text):
        add("email", m, _mask_email(m.group()))
    for m in _PHONE.finditer(text):
        add("phone", m, "XXXXXX" + (m.group(1) + m.group(2))[-4:])

    hits.sort(key=lambda h: (h.start, -(h.end - h.start)))
    kept: list[PiiHit] = []
    for h in hits:  # an Aadhaar-looking run inside a GSTIN etc. must not be reported twice
        if not kept or h.start >= kept[-1].end:
            kept.append(h)
    return kept


def redact(text: str) -> str:
    """The text with every identifier replaced by its masked form."""
    out, last = [], 0
    for h in find_pii(text):
        out.append(text[last:h.start])
        out.append(h.masked)
        last = h.end
    out.append(text[last:])
    return "".join(out)


def summarise(text: str) -> dict:
    hits = find_pii(text)
    counts: dict[str, int] = {}
    for h in hits:
        counts[h.kind] = counts.get(h.kind, 0) + 1
    return {"total": len(hits), "counts": counts, "items": [{"kind": h.kind, "label": KINDS[h.kind], "masked": h.masked} for h in hits]}
