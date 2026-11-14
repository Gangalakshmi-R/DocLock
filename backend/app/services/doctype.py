"""Rule-based document-type detection and a "is anything important missing?" checklist.

Why rules and not the LLM: it is instant, deterministic and testable, and the result is explainable
(``matched`` lists the words that decided it). The LLM is kept for the open-ended fact extraction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# type -> (label, {keyword: weight})
SIGNATURES: dict[str, tuple[str, dict[str, float]]] = {
    "insurance_policy": ("Insurance policy", {"policy": 1, "insured": 2, "premium": 2, "sum insured": 3, "waiting period": 2,
                                              "claim": 1, "cashless": 2, "insurer": 2, "exclusions": 1.5, "policy period": 3}),
    "rental_agreement": ("Rental agreement", {"tenant": 3, "landlord": 3, "lessor": 2, "lessee": 2, "security deposit": 3,
                                              "monthly rent": 3, "lease": 2, "rent": 1, "premises": 1, "lock-in": 2}),
    "fee_circular": ("Fee / college circular", {"fee": 2, "semester": 2, "scholarship": 2, "last date": 2, "circular": 3,
                                               "students": 1, "tuition": 2, "fine": 1, "hostel": 1, "examination": 1}),
    "warranty": ("Warranty / invoice", {"warranty": 3, "invoice": 2, "serial number": 3, "gst": 1, "model": 1,
                                        "purchase date": 2, "service centre": 2, "bill no": 2}),
    "bank_statement": ("Bank document", {"ifsc": 3, "account number": 3, "balance": 2, "debit": 2, "credit": 2,
                                         "transaction": 2, "statement": 2, "branch": 1}),
    "id_document": ("Identity document", {"aadhaar": 3, "permanent account number": 3, "date of birth": 2, "dob": 1,
                                          "income tax": 1, "passport": 3, "driving licence": 3, "voter": 2}),
    "study_notes": ("Study notes", {"algorithm": 2, "gradient": 2, "regularization": 2, "supervised": 2, "neural": 2,
                                    "theorem": 2, "chapter": 1, "revision": 2, "overfitting": 2, "model": 0.5}),
}

# type -> [(what to look for, regex)]. "found" means the pattern appears in the text.
CHECKLISTS: dict[str, list[tuple[str, str]]] = {
    "insurance_policy": [("Policy period / expiry date", r"policy period|expiry|expires|valid (?:till|until|upto)|renewal"),
                         ("Sum insured", r"sum insured|coverage amount|insured amount"),
                         ("Premium", r"premium"), ("Waiting period", r"waiting period"),
                         ("Exclusions", r"exclusions?|not covered"), ("Claim procedure / contact", r"claim|toll[- ]free|helpline")],
    "rental_agreement": [("Monthly rent", r"monthly rent|rent of|rent is"), ("Security deposit", r"security deposit|advance"),
                         ("Lease term", r"lease (?:term|period)|period of|months from|commenc"),
                         ("Notice period", r"notice"), ("Lock-in / termination", r"lock-in|terminat"),
                         ("Maintenance / repairs", r"maintenance|repairs?")],
    "fee_circular": [("Fee amount", r"fee|rs\.?|₹"), ("Last date / deadline", r"last date|on or before|due date|deadline"),
                     ("Late fine / penalty", r"fine|penalty|late fee"), ("Scholarship / concession", r"scholarship|concession")],
    "warranty": [("Purchase date", r"purchase date|date of purchase|invoice date"), ("Warranty period", r"warranty"),
                 ("Serial / model number", r"serial|model"), ("Service contact", r"service|helpline|toll")],
}
MIN_SCORE = 4.0


@dataclass(frozen=True)
class DocType:
    key: str
    label: str
    confidence: float  # 0..1, share of the winning score among all scores
    matched: tuple[str, ...]


def classify(text: str, filename: str = "") -> DocType:
    haystack = f"{filename} {text}".lower()
    scores: dict[str, float] = {}
    matched: dict[str, list[str]] = {}
    for key, (_, words) in SIGNATURES.items():
        for word, weight in words.items():
            if re.search(rf"\b{re.escape(word)}", haystack):
                scores[key] = scores.get(key, 0) + weight
                matched.setdefault(key, []).append(word)
    if not scores:
        return DocType("other", "Other document", 0.0, ())
    best = max(scores, key=scores.get)
    if scores[best] < MIN_SCORE:
        return DocType("other", "Other document", 0.0, ())
    return DocType(best, SIGNATURES[best][0], round(scores[best] / sum(scores.values()), 2), tuple(matched[best]))


def checklist(doc_type: str, text: str) -> list[dict]:
    """For types with a checklist: which expected items appear in the text and which do not."""
    lowered = text.lower()
    return [{"item": label, "found": bool(re.search(pattern, lowered))} for label, pattern in CHECKLISTS.get(doc_type, [])]
