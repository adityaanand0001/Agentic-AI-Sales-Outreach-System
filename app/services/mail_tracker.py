"""Mail Agent Tracker — updates Supabase with email campaign status."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from supabase import Client

from app.config.settings import get_settings
from app.models.schemas import MailAgentTracker

logger = logging.getLogger(__name__)


class MailTrackerService:
    """Manages the mail_agent_tracker table records."""

    def __init__(self, db: Client) -> None:
        self.db = db
        self.settings = get_settings()
        self.table = self.settings.supabase_mail_agent_table

    # ── Create ──────────────────────────────────────────────────────────────────

    def create_record(
        self,
        company_name: str,
        email: str,
        subject: str = "",
        body_preview: str = "",
        context: str = "",
        status: str = "PENDING",
        thread_id: str | None = None,
        gmail_message_id: str | None = None,
        is_reply: bool = False,
    ) -> dict:
        """Insert a new tracker record and return it."""
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "id": str(uuid.uuid4()),
            "company_name": company_name,
            "email": email,
            "mail_count": 1,
            "status": status,
            "context": context,
            "email_subject": subject,
            "email_body_preview": body_preview,
            "thread_id": thread_id,
            "gmail_message_id": gmail_message_id,
            "is_reply": is_reply,
            "created_at": now,
            "updated_at": now,
        }
        self.db.table(self.table).insert(record).execute()
        logger.info("Tracker record created: %s — %s", record["id"], company_name)
        return record

    # ── Read ────────────────────────────────────────────────────────────────────

    def get_record(self, tracker_id: str) -> dict | None:
        resp = (
            self.db.table(self.table)
            .select("*")
            .eq("id", tracker_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0] if rows else None

    def list_records(
        self,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        q = self.db.table(self.table).select("*").order("created_at", desc=True).limit(limit).range(offset, offset + limit - 1)
        if status:
            q = q.eq("status", status)
        resp = q.execute()
        return resp.data or []

    def get_summary(self) -> dict:
        """Return counts grouped by status."""
        resp = self.db.table(self.table).select("status").execute()
        rows = resp.data or []
        counts = {"total": len(rows), "PENDING": 0, "APPROVED": 0, "SENT": 0, "REJECTED": 0, "FAILED": 0}
        for r in rows:
            s = r.get("status", "PENDING")
            if s in counts:
                counts[s] += 1
        return counts

    def find_sent_by_thread(self, thread_id: str) -> list[dict]:
        """Find SENT tracker records matching a Gmail thread ID."""
        resp = (
            self.db.table(self.table)
            .select("*")
            .eq("thread_id", thread_id)
            .eq("status", "SENT")
            .execute()
        )
        return resp.data or []

    def find_by_gmail_message_id(self, gmail_message_id: str) -> dict | None:
        """Find a tracker record by its Gmail message ID."""
        resp = (
            self.db.table(self.table)
            .select("id")
            .eq("gmail_message_id", gmail_message_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0] if rows else None

    # ── Update ──────────────────────────────────────────────────────────────────

    def update_status(self, tracker_id: str, status: str, **extra) -> dict | None:
        now = datetime.now(timezone.utc).isoformat()
        payload = {"status": status, "updated_at": now, **extra}
        self.db.table(self.table).update(payload).eq("id", tracker_id).execute()
        logger.info("Tracker %s → %s", tracker_id, status)
        return self.get_record(tracker_id)

    def update_record(self, tracker_id: str, **updates) -> dict | None:
        """Update any fields in the tracker record."""
        now = datetime.now(timezone.utc).isoformat()
        payload = {"updated_at": now, **updates}
        self.db.table(self.table).update(payload).eq("id", tracker_id).execute()
        logger.info("Tracker record %s updated", tracker_id)
        return self.get_record(tracker_id)

    def increment_mail_count(self, tracker_id: str) -> None:
        record = self.get_record(tracker_id)
        if record:
            new_count = (record.get("mail_count") or 0) + 1
            self.db.table(self.table).update(
                {"mail_count": new_count, "updated_at": datetime.now(timezone.utc).isoformat()}
            ).eq("id", tracker_id).execute()
