"""Export deadline alerts as an iCalendar (.ics) file for Google/Apple/Outlook calendars.

All-day events with two reminders (7 days and 1 day before). UIDs are stable, so re-importing the file
updates the existing events instead of duplicating them.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", r"\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """RFC 5545: lines are at most 75 octets; continuation lines start with one space."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return [line]
    parts, current, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > (75 if not parts else 74):
            parts.append(current)
            current, size = "", 0
        current += ch
        size += n
    parts.append(current)
    return [parts[0]] + [" " + p for p in parts[1:]]


def build_ics(alerts: list[dict], now: datetime | None = None) -> str:
    """``alerts`` are the dicts produced by schemas.alert_json."""
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//DocLock//Deadline alerts//EN", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:DocLock deadlines"]
    for a in alerts:
        day = date.fromisoformat(a["deadline"])
        summary = f"{a['title']} - {a['filename']}" if a.get("filename") else a["title"]
        description = (a.get("description") or "") + "\nAuto-extracted by DocLock: verify against the original document."
        lines += ["BEGIN:VEVENT", f"UID:doclock-alert-{a['id']}@doclock.local", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{_escape(summary)}", f"DESCRIPTION:{_escape(description.strip())}", "TRANSP:TRANSPARENT"]
        for trigger, label in (("-P7D", "in 7 days"), ("-P1D", "tomorrow")):
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_escape(a['title'])} {label}", f"TRIGGER:{trigger}", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(folded for line in lines for folded in _fold(line)) + "\r\n"
