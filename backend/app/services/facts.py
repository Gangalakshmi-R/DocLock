"""Document intelligence: pull dates, deadlines and amounts out of a document and turn them into alerts.

Two extractors are combined:

1. A deterministic regex extractor (always runs, fully unit-tested). It finds dates in the common
   numeric / textual formats and labels them EXPIRY / RENEWAL / DUE / DEADLINE from the words around them.
2. An optional LLM extractor (Llama 3.1 via Ollama) that can pick up facts the regexes miss. Its output is
   *never trusted*: every value must be grounded in the document text, otherwise it is dropped, so the
   model cannot invent a deadline.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from app import config
from app.services import llm

DEADLINE_KINDS = ("EXPIRY", "RENEWAL", "DUE", "DEADLINE")
FACT_TYPES = ("DATE", "AMOUNT", "ID", "ORGANIZATION", "PERSON", "OTHER")
MAX_FACTS = 60
MAX_PLAIN_DATES = 10
MAX_AMOUNTS = 15
MIN_YEAR, MAX_YEAR = 1990, 2100
STALE_ALERT_DAYS = 365  # do not raise alerts for dates more than a year in the past

_MONTH = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_MONTH_NUM = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

_ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_NUMERIC = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\b")
_DMY_TEXT = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH})\.?,?\s+(\d{{4}})\b", re.I)
_MDY_TEXT = re.compile(rf"\b({_MONTH})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I)

# Checked in order of the *closest* keyword before the date (see _classify).
_KIND_KEYWORDS: dict[str, tuple[str, ...]] = {
    "EXPIRY": ("expiry", "expires", "expire", "expiration", "valid until", "valid till", "valid through",
               "valid upto", "valid up to", "validity", "ends on", "end date", "lapses"),
    "RENEWAL": ("renewal", "renew"),
    "DUE": ("due date", "due on", "due by", "due", "payable by", "pay by", "payment date"),
    "DEADLINE": ("deadline", "last date", "submit by", "submitted by", "apply by", "register by",
                 "no later than", "on or before", "not later than"),
}
_RANGE_JOINER = re.compile(r"^\s*(?:to|until|till|through|thru|–|-|—)\s*$", re.I)
_TAIL_STOPWORDS = {"is", "are", "on", "by", "the", "of", "to", "from", "till", "until", "and", "a", "an", "at", "in",
                   "will", "be", "shall", "must", "before", "no", "later", "than", "or", "for", "as", "per", "with"}

_CURRENCY = r"(?:₹|\$|€|£|\b(?:Rs\.?|INR|USD|EUR|GBP))"
_AMOUNT_PREFIX = re.compile(rf"{_CURRENCY}\s?\d[\d,]*(?:\.\d{{1,2}})?(?:\s?(?:lakhs?|crores?|million|billion))?", re.I)
_AMOUNT_SUFFIX = re.compile(r"\b\d[\d,]*(?:\.\d{1,2})?\s?(?:INR|USD|EUR|GBP|rupees|dollars)\b", re.I)


@dataclass(frozen=True)
class ExtractedFact:
    fact_type: str
    key_name: str
    value: str
    deadline: Optional[date] = None
    deadline_kind: Optional[str] = None
    context: str = field(default="", compare=False)


@dataclass(frozen=True)
class _DateHit:
    start: int
    end: int
    value: date


# --------------------------------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------------------------------
def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    if not MIN_YEAR <= year <= MAX_YEAR:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def find_dates(text: str) -> list[_DateHit]:
    """All recognisable calendar dates in *text*, in order, without overlaps."""
    hits: list[_DateHit] = []
    for m in _ISO.finditer(text):
        d = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            hits.append(_DateHit(m.start(), m.end(), d))
    for m in _NUMERIC.finditer(text):
        a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        first, second = (a, b) if config.DATES_DAY_FIRST else (b, a)  # (day, month)
        d = _safe_date(year, second, first) or _safe_date(year, first, second)  # tolerate the other order
        if d:
            hits.append(_DateHit(m.start(), m.end(), d))
    for m in _DMY_TEXT.finditer(text):
        d = _safe_date(int(m.group(3)), _MONTH_NUM[m.group(2)[:3].lower()], int(m.group(1)))
        if d:
            hits.append(_DateHit(m.start(), m.end(), d))
    for m in _MDY_TEXT.finditer(text):
        d = _safe_date(int(m.group(3)), _MONTH_NUM[m.group(1)[:3].lower()], int(m.group(2)))
        if d:
            hits.append(_DateHit(m.start(), m.end(), d))

    hits.sort(key=lambda h: (h.start, -(h.end - h.start)))
    result: list[_DateHit] = []
    for h in hits:
        if result and h.start < result[-1].end:
            continue  # overlaps a longer/earlier match
        result.append(h)
    return result


def _line_context(text: str, start: int, end: int) -> tuple[str, str]:
    """(text before the date within its sentence, the surrounding sentence/line for display)."""
    window_start = max(0, start - 120)
    before = text[window_start:start]
    cut = max(before.rfind("\n"), before.rfind(". "), before.rfind("; "))
    if cut != -1:
        before = before[cut + 1:]
    after = text[end:end + 80]
    after_cut = min([i for i in (after.find("\n"), after.find(". ")) if i != -1], default=len(after))
    snippet = re.sub(r"\s+", " ", (before + text[start:end] + after[:after_cut])).strip(" .;:-")
    return before, snippet[:200]


def _classify(before: str) -> Optional[str]:
    """Deadline kind from the keyword that sits closest to the date (rightmost in *before*)."""
    lowered = before.lower()
    best_kind, best_pos = None, -1
    for kind, words in _KIND_KEYWORDS.items():
        for word in words:
            pos = lowered.rfind(word)
            if pos > best_pos:
                best_kind, best_pos = kind, pos
    return best_kind


def _label_from(before: str, max_words: int = 5) -> str:
    """Human label for a fact: the last few words before it, e.g. 'Scholarship application deadline'."""
    core = before.rstrip(" \t:–—-=(")  # "Policy expiry date: " -> "Policy expiry date"
    last_line = core.split("\n")[-1]
    if ":" in last_line:  # "Policy: expires on" -> use the part after the colon when it has content
        tail = last_line.rsplit(":", 1)[1]
        if tail.strip():
            last_line = tail
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", last_line)
    while words and words[-1].lower() in _TAIL_STOPWORDS:
        words.pop()
    words = words[-max_words:]
    while words and words[0].lower() in {"the", "a", "an", "and", "or", "of", "is", "are"}:
        words.pop(0)
    return " ".join(words)


def _snake(label: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return (slug or fallback)[:100]


def extract_date_facts(text: str) -> list[ExtractedFact]:
    facts: list[ExtractedFact] = []
    plain = 0
    previous: Optional[_DateHit] = None
    for hit in find_dates(text):
        before, snippet = _line_context(text, hit.start, hit.end)
        kind = _classify(before)
        label = _label_from(before, max_words=7)
        if kind is None and previous is not None and _RANGE_JOINER.match(text[previous.end:hit.start]):
            kind = "EXPIRY"  # "15 March 2026 to 14 March 2027": the second date ends the period
            label = ""       # the words before it belong to the first date, so use the generic label
        previous = hit
        if kind:
            facts.append(ExtractedFact("DATE", _snake(label, f"{kind.lower()}_date"), hit.value.isoformat(), hit.value, kind, snippet))
        elif plain < MAX_PLAIN_DATES:
            plain += 1
            facts.append(ExtractedFact("DATE", _snake(label, "date_mentioned"), hit.value.isoformat(), None, None, snippet))
    return facts


# --------------------------------------------------------------------------------------------------
# Amounts
# --------------------------------------------------------------------------------------------------
def extract_amount_facts(text: str) -> list[ExtractedFact]:
    found: list[tuple[int, int]] = []
    for pattern in (_AMOUNT_PREFIX, _AMOUNT_SUFFIX):
        found.extend((m.start(), m.end()) for m in pattern.finditer(text))
    found.sort()
    facts: list[ExtractedFact] = []
    seen: set[tuple[str, str]] = set()
    last_end = -1
    for start, end in found:
        if start < last_end:
            continue
        last_end = end
        value = re.sub(r"\s+", " ", text[start:end]).strip().rstrip(",.")
        before, snippet = _line_context(text, start, end)
        key = _snake(_label_from(before, max_words=4), "amount")
        if (key, value) in seen:
            continue
        seen.add((key, value))
        facts.append(ExtractedFact("AMOUNT", key, value, context=snippet))
        if len(facts) >= MAX_AMOUNTS:
            break
    return facts


def extract_facts_regex(text: str) -> list[ExtractedFact]:
    return extract_date_facts(text) + extract_amount_facts(text)


# --------------------------------------------------------------------------------------------------
# LLM output: parse, validate, ground
# --------------------------------------------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def parse_llm_facts(raw: str, document_text: str) -> list[ExtractedFact]:
    """Turn the model's JSON into validated facts. Anything not grounded in *document_text* is discarded."""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    items = data.get("facts") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []

    known_dates = {h.value for h in find_dates(document_text)}
    text_norm = _norm(document_text)
    facts: list[ExtractedFact] = []
    for item in items[:25]:
        if not isinstance(item, dict):
            continue
        value = str(item.get("value") or "").strip()[:500]
        if not value:
            continue
        fact_type = str(item.get("type") or "OTHER").upper()
        fact_type = fact_type if fact_type in FACT_TYPES else "OTHER"
        name = _snake(str(item.get("name") or ""), fact_type.lower())

        deadline: Optional[date] = None
        kind: Optional[str] = None
        raw_deadline = item.get("deadline")
        if isinstance(raw_deadline, str) and raw_deadline.strip():
            try:
                parsed = date.fromisoformat(raw_deadline.strip()[:10])
            except ValueError:
                parsed = None
            if parsed and parsed in known_dates:  # grounded: this exact date is written in the document
                deadline = parsed
                raw_kind = str(item.get("deadline_kind") or "DEADLINE").upper()
                kind = raw_kind if raw_kind in DEADLINE_KINDS else "DEADLINE"
        if deadline is not None:
            value = deadline.isoformat()
        elif _norm(value) not in text_norm:
            continue  # not literally in the document -> treat as a hallucination
        facts.append(ExtractedFact(fact_type, name, value, deadline, kind))
    return facts


def merge_facts(primary: list[ExtractedFact], extra: list[ExtractedFact]) -> list[ExtractedFact]:
    """primary wins; extra facts are added only if they are not duplicates. Capped at MAX_FACTS."""
    merged = list(primary)
    seen_values = {(f.fact_type, _norm(f.value)) for f in merged}
    seen_deadlines = {f.deadline for f in merged if f.deadline}
    for f in extra:
        if (f.fact_type, _norm(f.value)) in seen_values:
            continue
        if f.deadline and f.deadline in seen_deadlines:
            continue
        merged.append(f)
        seen_values.add((f.fact_type, _norm(f.value)))
        if f.deadline:
            seen_deadlines.add(f.deadline)
    return merged[:MAX_FACTS]


def extract_facts(text: str, use_llm: Optional[bool] = None) -> list[ExtractedFact]:
    """Regex facts, plus validated LLM facts when enabled. The LLM step can never fail the pipeline."""
    facts = extract_facts_regex(text)
    use_llm = config.LLM_FACTS_ENABLED if use_llm is None else use_llm
    if use_llm and text.strip():
        try:
            facts = merge_facts(facts, parse_llm_facts(llm.request_fact_json(text), text))
        except Exception as exc:  # network error, timeout, model not loaded ... regex facts are still good
            print(f"LLM fact extraction skipped: {exc}")
    return facts


# --------------------------------------------------------------------------------------------------
# Alerts
# --------------------------------------------------------------------------------------------------
_KIND_TITLES = {"EXPIRY": "Expires", "RENEWAL": "Renewal", "DUE": "Payment due", "DEADLINE": "Deadline"}


def alerts_from_facts(facts: list[ExtractedFact], today: Optional[date] = None) -> list[dict]:
    """Alert rows (title, description, deadline_date, alert_type) for dated facts. De-duplicated."""
    today = today or date.today()
    oldest = today - timedelta(days=STALE_ALERT_DAYS)
    alerts: list[dict] = []
    seen: set[tuple[date, str]] = set()
    for f in facts:
        if not f.deadline or not f.deadline_kind or f.deadline < oldest:
            continue
        key = (f.deadline, f.deadline_kind)
        if key in seen:
            continue
        seen.add(key)
        label = f.key_name.replace("_", " ").strip().capitalize()
        generic = f.key_name in {f"{f.deadline_kind.lower()}_date", "date_mentioned"}
        title = _KIND_TITLES[f.deadline_kind] if generic or not label else label
        alerts.append({
            "title": title[:200],
            "description": (f.context or "")[:500] or None,
            "deadline_date": f.deadline,
            "alert_type": f.deadline_kind,
        })
    alerts.sort(key=lambda a: a["deadline_date"])
    return alerts
