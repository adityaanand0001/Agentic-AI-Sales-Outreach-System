"""Send Scheduler — manages scheduled (delayed) email sends."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from supabase import Client

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class SendSchedulerService:
    """Manages the mail_agent_schedule_queue table for scheduled email sends."""

    def __init__(self, db: Client) -> None:
        self.db = db
        self.settings = get_settings()
        self.table = "mail_agent_schedule_queue"

    def create_schedule(
        self,
        tracker_id: str,
        scheduled_at: str,
        company_name: str = "",
        email: str = "",
        email_subject: str = "",
        email_body_preview: str = "",
    ) -> dict:
        """Schedule an email for future delivery."""
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "id": str(uuid.uuid4()),
            "tracker_id": tracker_id,
            "company_name": company_name,
            "email": email,
            "email_subject": email_subject,
            "email_body_preview": email_body_preview,
            "scheduled_at": scheduled_at,
            "status": "PENDING",
            "error": "",
            "created_at": now,
            "updated_at": now,
        }
        self.db.table(self.table).insert(record).execute()
        logger.info(
            "Scheduled send created: %s — tracker=%s, scheduled=%s",
            record["id"], tracker_id, scheduled_at,
        )
        return record

    def approve_and_schedule(
        self,
        tracker_id: str,
        scheduled_at: str,
        company_name: str = "",
        email: str = "",
        email_subject: str = "",
        email_body_preview: str = "",
    ) -> dict:
        """Approve and schedule in one step (writes to both tracker and schedule queue)."""
        # Update tracker status to APPROVED
        now = datetime.now(timezone.utc).isoformat()
        self.db.table(self.settings.supabase_mail_agent_table).update(
            {"status": "APPROVED", "updated_at": now}
        ).eq("id", tracker_id).execute()

        # Create schedule entry
        return self.create_schedule(
            tracker_id=tracker_id,
            scheduled_at=scheduled_at,
            company_name=company_name,
            email=email,
            email_subject=email_subject,
            email_body_preview=email_body_preview,
        )

    def list_scheduled(
        self,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """List scheduled sends, optionally filtered by status."""
        q = (
            self.db.table(self.table)
            .select("*")
            .order("scheduled_at", desc=False)
            .limit(limit)
            .range(offset, offset + limit - 1)
        )
        if status:
            q = q.eq("status", status)
        resp = q.execute()
        return resp.data or []

    def get_schedule(self, schedule_id: str) -> dict | None:
        """Get a single schedule entry."""
        resp = (
            self.db.table(self.table)
            .select("*")
            .eq("id", schedule_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0] if rows else None

    def cancel_schedule(self, schedule_id: str) -> dict | None:
        """Cancel a pending scheduled send."""
        record = self.get_schedule(schedule_id)
        if not record:
            return None
        if record["status"] not in ("PENDING",):
            return None

        now = datetime.now(timezone.utc).isoformat()
        self.db.table(self.table).update(
            {"status": "CANCELLED", "updated_at": now}
        ).eq("id", schedule_id).execute()

        # Also revert tracker status back to PENDING
        self.db.table(self.settings.supabase_mail_agent_table).update(
            {"status": "PENDING", "updated_at": now}
        ).eq("id", record["tracker_id"]).execute()

        logger.info("Schedule cancelled: %s", schedule_id)
        return self.get_schedule(schedule_id)

    def process_due(self) -> list[dict]:
        """Find and return all due (ready-to-send) schedule entries."""
        now = datetime.now(timezone.utc).isoformat()
        resp = (
            self.db.table(self.table)
            .select("*")
            .eq("status", "PENDING")
            .lte("scheduled_at", now)
            .limit(50)
            .execute()
        )
        due = resp.data or []

        # Mark them as PROCESSING to avoid double-processing
        ids = [r["id"] for r in due if r.get("id")]
        if ids:
            self.db.table(self.table).update(
                {"status": "PROCESSING", "updated_at": now}
            ).in_("id", ids).execute()

        return due

    def mark_sent(self, schedule_id: str) -> None:
        """Mark a schedule entry as sent."""
        now = datetime.now(timezone.utc).isoformat()
        self.db.table(self.table).update(
            {"status": "SENT", "updated_at": now}
        ).eq("id", schedule_id).execute()

    def mark_failed(self, schedule_id: str, error: str) -> None:
        """Mark a schedule entry as failed."""
        now = datetime.now(timezone.utc).isoformat()
        self.db.table(self.table).update(
            {"status": "FAILED", "error": error, "updated_at": now}
        ).eq("id", schedule_id).execute()

    def get_summary(self) -> dict:
        """Get counts by status."""
        resp = self.db.table(self.table).select("status").execute()
        rows = resp.data or []
        counts: dict[str, int] = {"total": len(rows), "PENDING": 0, "SENT": 0, "CANCELLED": 0, "FAILED": 0}
        for r in rows:
            s = r.get("status", "")
            if s in counts:
                counts[s] += 1
        return counts
