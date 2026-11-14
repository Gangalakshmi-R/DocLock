from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Document, DocumentAlert
from app.schemas import alert_json
from app.security import current_user
from app.services.calendar_ics import build_ics

router = APIRouter(prefix="/api/alerts", tags=["alerts"], dependencies=[Depends(current_user)])


class AlertPatch(BaseModel):
    acknowledged: bool


@router.get("")
def list_alerts(includeAcknowledged: bool = Query(default=False), withinDays: Optional[int] = Query(default=None, ge=0, le=3650),
                db: Session = Depends(get_db)):
    """Deadlines and expiries found in your documents, soonest first (overdue ones lead the list)."""
    stmt = (select(DocumentAlert, Document.original_filename)
            .join(Document, Document.id == DocumentAlert.document_id, isouter=True)
            .order_by(DocumentAlert.deadline_date.asc(), DocumentAlert.id.asc()))
    if not includeAcknowledged:
        stmt = stmt.where(DocumentAlert.is_acknowledged.is_(False))
    if withinDays is not None:
        stmt = stmt.where(DocumentAlert.deadline_date <= date.today() + timedelta(days=withinDays))
    items = [alert_json(alert, filename) for alert, filename in db.execute(stmt).all()]
    summary = {
        "overdue": sum(1 for a in items if a["status"] == "OVERDUE"),
        "dueSoon": sum(1 for a in items if a["status"] == "DUE_SOON"),
        "upcoming": sum(1 for a in items if a["status"] == "UPCOMING"),
    }
    return {"alerts": items, "summary": summary}


@router.get("/calendar.ics")
def export_calendar(db: Session = Depends(get_db)):
    """Open deadlines as an .ics file: import into Google / Apple / Outlook calendar for phone reminders."""
    stmt = (select(DocumentAlert, Document.original_filename)
            .join(Document, Document.id == DocumentAlert.document_id, isouter=True)
            .where(DocumentAlert.is_acknowledged.is_(False)).order_by(DocumentAlert.deadline_date.asc()))
    items = [alert_json(alert, filename) for alert, filename in db.execute(stmt).all()]
    return Response(build_ics(items), media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="doclock-deadlines.ics"'})


@router.patch("/{alert_id}")
def update_alert(alert_id: int, body: AlertPatch, db: Session = Depends(get_db)):
    alert = db.get(DocumentAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")
    alert.is_acknowledged = body.acknowledged
    db.commit()
    doc = db.get(Document, alert.document_id) if alert.document_id else None
    return alert_json(alert, doc.original_filename if doc else None)
