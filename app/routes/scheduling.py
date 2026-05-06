"""API routes for Smart Send Scheduling."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.deps.container import get_gmail_service, get_mail_tracker
from app.models.schemas import ScheduleApproveRequest, ScheduleCreate, ScheduleItem, ScheduleSummary
from app.services.send_scheduler import SendSchedulerService
from app.services.gmail_oauth import GmailOAuthService
from app.services.mail_tracker import MailTrackerService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scheduling", tags=["scheduling"])


def get_scheduler() -> SendSchedulerService:
    """Get a fresh scheduler instance (injected via deps normally)."""
    from app.config.database import get_supabase
    return SendSchedulerService(db=get_supabase())


@router.post("/schedule", response_model=ScheduleItem)
def schedule_send(
    req: ScheduleCreate,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Schedule a pending email for future delivery (approve + schedule)."""
    record = tracker.get_record(req.tracker_id)
    if not record:
        raise HTTPException(404, "Tracker record not found")
    if record["status"] != "PENDING":
        raise HTTPException(400, f"Cannot schedule email with status {record['status']}")

    scheduler = get_scheduler()
    item = scheduler.approve_and_schedule(
        tracker_id=req.tracker_id,
        scheduled_at=req.scheduled_at,
        company_name=record.get("company_name", ""),
        email=record.get("email", ""),
        email_subject=record.get("email_subject", ""),
        email_body_preview=record.get("email_body_preview", ""),
    )
    return ScheduleItem(**item)


@router.get("/list", response_model=list[ScheduleItem])
def list_scheduled_sends(
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """List all scheduled sends, optionally filtered by status."""
    scheduler = get_scheduler()
    items = scheduler.list_scheduled(status=status, limit=limit, offset=offset)
    return [ScheduleItem(**i) for i in items]


@router.get("/{schedule_id}", response_model=ScheduleItem)
def get_scheduled_send(schedule_id: str):
    """Get a single scheduled send entry."""
    scheduler = get_scheduler()
    item = scheduler.get_schedule(schedule_id)
    if not item:
        raise HTTPException(404, "Scheduled send not found")
    return ScheduleItem(**item)


@router.delete("/{schedule_id}")
def cancel_scheduled_send(schedule_id: str):
    """Cancel a pending scheduled send (reverts tracker to PENDING)."""
    scheduler = get_scheduler()
    result = scheduler.cancel_schedule(schedule_id)
    if result is None:
        raise HTTPException(400, "Cannot cancel — not found or already processed")
    return {"message": "Scheduled send cancelled", "schedule_id": schedule_id}


@router.post("/process-due")
def process_due_sends(
    gmail_service: GmailOAuthService = Depends(get_gmail_service),
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Process all due scheduled sends — send emails and update status."""
    scheduler = get_scheduler()
    due = scheduler.process_due()
    results = []

    for item in due:
        sid = item["id"]
        tid = item["tracker_id"]
        try:
            msg_id, thread_id = gmail_service.safe_send_email(
                recipient=item.get("email", ""),
                subject=item.get("email_subject", ""),
                body_text=item.get("email_body_preview", ""),
            )
            # Update tracker to SENT
            tracker.update_status(tid, "SENT", gmail_message_id=msg_id, thread_id=thread_id)
            # Mark schedule as SENT
            scheduler.mark_sent(sid)
            results.append({"schedule_id": sid, "tracker_id": tid, "status": "SENT"})
            logger.info("Scheduled send executed: %s → %s", sid, item.get("email"))
        except Exception as e:
            logger.error("Scheduled send failed %s: %s", sid, e)
            tracker.update_status(tid, "FAILED", error=str(e))
            scheduler.mark_failed(sid, str(e))
            results.append({"schedule_id": sid, "tracker_id": tid, "status": "FAILED", "error": str(e)})

    return {"processed": len(results), "results": results}


@router.get("/summary", response_model=ScheduleSummary)
def get_schedule_summary():
    """Get counts of scheduled sends by status."""
    scheduler = get_scheduler()
    counts = scheduler.get_summary()
    return ScheduleSummary(
        total=counts.get("total", 0),
        pending=counts.get("PENDING", 0),
        sent=counts.get("SENT", 0),
        cancelled=counts.get("CANCELLED", 0),
        failed=counts.get("FAILED", 0),
    )
