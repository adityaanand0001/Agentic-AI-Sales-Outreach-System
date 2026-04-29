"""Lead ingestion from a configurable Supabase table."""

from __future__ import annotations

import logging

from supabase import Client

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class LeadIngestionService:
    """Fetches company leads from the configured Supabase table."""

    def __init__(self, db: Client) -> None:
        self.db = db
        self.settings = get_settings()
        self.table = self.settings.supabase_leads_table

    def fetch_pending_leads(self, limit: int | None = None, offset: int = 0) -> list[dict]:
        """Fetch leads from the configured table.

        Note: The source table has NO status column, so this fetches ALL leads.
        We process them one by one based on name, context, and email columns only.
        Pagination is used to iterate through all leads.
        """
        fetch_limit = limit or self.settings.ingest_batch_size
        resp = (
            self.db.table(self.table)
            .select("*")
            .order("created_at", desc=True)
            .range(offset, offset + fetch_limit - 1)
            .execute()
        )
        return resp.data or []

    def fetch_lead_by_id(self, lead_id: str) -> dict | None:
        resp = (
            self.db.table(self.table)
            .select("*")
            .eq("id", lead_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0] if rows else None

    def fetch_lead_by_email(self, email: str) -> dict | None:
        resp = (
            self.db.table(self.table)
            .select("*")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0] if rows else None

    def mark_processing(self, lead_id: str) -> None:
        """Placeholder: Source table has NO status column, so we cannot mark leads as processed.

        If you add a status column to your source table later, implement logic here
        to update the lead status (e.g., to 'PROCESSING' or 'PROCESSED').
        """
        # Source table doesn't have status column, so we cannot track processing state
        # We process leads one by one based on name, context, and email columns only
        pass
