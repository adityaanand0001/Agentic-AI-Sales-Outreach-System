"""Follow-up / Re-engagement Engine — auto-schedule follow-ups for unreplied leads."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from supabase import Client

from app.config.settings import get_settings
from app.services.email_generator import EmailGeneratorService
from app.services.mail_tracker import MailTrackerService
from app.services.ingestion import LeadIngestionService

logger = logging.getLogger(__name__)


class FollowUpService:
    """Manages follow-up rules and generates follow-up emails for unreplied leads."""

    def __init__(
        self,
        db: Client,
        tracker: MailTrackerService,
        ingestion: LeadIngestionService,
        email_gen: EmailGeneratorService,
    ) -> None:
        self.db = db
        self.tracker = tracker
        self.ingestion = ingestion
        self.email_gen = email_gen
        self.settings = get_settings()
        self.rules_table = "mail_agent_follow_up_rules"
        self.instances_table = "mail_agent_follow_ups"

    # ── Rules CRUD ───────────────────────────────────────────────────────────

    def list_rules(self) -> list[dict]:
        resp = (
            self.db.table(self.rules_table)
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return resp.data or []

    def get_rule(self, rule_id: str) -> dict | None:
        resp = (
            self.db.table(self.rules_table)
            .select("*")
            .eq("id", rule_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0] if rows else None

    def create_rule(self, name: str, delay_days: int = 3, max_follow_ups: int = 3) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "id": str(uuid.uuid4()),
            "name": name,
            "delay_days": delay_days,
            "max_follow_ups": max_follow_ups,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        self.db.table(self.rules_table).insert(record).execute()
        logger.info("Follow-up rule created: %s — %s (delay=%d, max=%d)", record["id"], name, delay_days, max_follow_ups)
        return record

    def update_rule(self, rule_id: str, **updates) -> dict | None:
        now = datetime.now(timezone.utc).isoformat()
        payload = {"updated_at": now, **updates}
        self.db.table(self.rules_table).update(payload).eq("id", rule_id).execute()
        return self.get_rule(rule_id)

    def delete_rule(self, rule_id: str) -> None:
        self.db.table(self.rules_table).delete().eq("id", rule_id).execute()
        logger.info("Follow-up rule deleted: %s", rule_id)

    # ── Instance management ───────────────────────────────────────────────────

    def list_pending_follow_ups(self, limit: int = 100, offset: int = 0) -> list[dict]:
        resp = (
            self.db.table(self.instances_table)
            .select("*")
            .eq("status", "PENDING")
            .order("scheduled_at", desc=False)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return resp.data or []

    def list_follow_ups(
        self, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[dict]:
        q = (
            self.db.table(self.instances_table)
            .select("*")
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
        )
        if status:
            q = q.eq("status", status)
        resp = q.execute()
        return resp.data or []

    def get_follow_up(self, instance_id: str) -> dict | None:
        resp = (
            self.db.table(self.instances_table)
            .select("*")
            .eq("id", instance_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0] if rows else None

    def approve_follow_up(self, instance_id: str, gmail_service) -> dict | None:
        """Approve and send a follow-up email via Gmail."""
        instance = self.get_follow_up(instance_id)
        if not instance:
            logger.warning("Follow-up instance not found: %s", instance_id)
            return None
        if instance["status"] != "PENDING":
            logger.warning("Follow-up %s already %s", instance_id, instance["status"])
            return None

        try:
            msg_id, thread_id = gmail_service.safe_send_email(
                recipient=instance["email"],
                subject=instance["email_subject"],
                body_text=instance["email_body_preview"],
            )
            now = datetime.now(timezone.utc).isoformat()
            self.db.table(self.instances_table).update(
                {
                    "status": "SENT",
                    "gmail_message_id": msg_id,
                    "updated_at": now,
                }
            ).eq("id", instance_id).execute()
            logger.info("Follow-up sent: %s — %s", instance_id, instance["company_name"])
            return self.get_follow_up(instance_id)
        except Exception as e:
            logger.error("Failed to send follow-up %s: %s", instance_id, e)
            self.db.table(self.instances_table).update(
                {
                    "status": "FAILED",
                    "error": str(e),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", instance_id).execute()
            return self.get_follow_up(instance_id)

    def skip_follow_up(self, instance_id: str) -> dict | None:
        self.db.table(self.instances_table).update(
            {
                "status": "SKIPPED",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", instance_id).execute()
        return self.get_follow_up(instance_id)

    # ── Generation engine ────────────────────────────────────────────────────

    def generate_follow_ups(self, rule_id: str | None = None, dry_run: bool = False) -> dict:
        """
        Scan sent emails that haven't received replies and create follow-up instances.

        Args:
            rule_id: Only apply a specific rule. If None, applies all active rules.
            dry_run: If True, only report what would be generated without inserting.

        Returns:
            Summary dict with counts and details.
        """
        # 1. Gather applicable rules
        if rule_id:
            rule = self.get_rule(rule_id)
            rules = [rule] if rule else []
        else:
            rules = [r for r in self.list_rules() if r.get("is_active")]

        if not rules:
            return {"generated": 0, "message": "No active rules found", "details": []}

        # 2. Fetch all SENT tracker records (last 90 days)
        ninety_days_ago = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        sent_resp = (
            self.db.table(self.tracker.table)
            .select("*")
            .eq("status", "SENT")
            .gte("created_at", ninety_days_ago)
            .order("created_at", desc=True)
            .execute()
        )
        sent_emails = sent_resp.data or []

        if not sent_emails:
            return {"generated": 0, "message": "No sent emails found in last 90 days", "details": []}

        # 3. Identify which sent emails have received replies
        sent_by_email: dict[str, list[dict]] = {}
        for se in sent_emails:
            email = se.get("email", "")
            sent_by_email.setdefault(email, []).append(se)

        replied_emails: set[str] = set()
        reply_resp = (
            self.db.table(self.tracker.table)
            .select("email")
            .eq("status", "REPLY")
            .execute()
        )
        for r in reply_resp.data or []:
            replied_emails.add(r.get("email", ""))

        # 4. For each rule, check each sent email and decide if follow-up is needed
        now = datetime.now(timezone.utc)
        generated: list[dict] = []
        skipped: list[dict] = []

        for rule in rules:
            delay_days = rule.get("delay_days", 3)
            max_follow_ups = rule.get("max_follow_ups", 3)

            for se in sent_emails:
                email = se.get("email", "")
                tracker_id = se.get("id", "")

                # Skip replied leads
                if email in replied_emails:
                    continue

                sent_at_str = se.get("created_at") or se.get("updated_at") or ""
                if not sent_at_str:
                    continue

                try:
                    sent_at = datetime.fromisoformat(sent_at_str)
                except ValueError:
                    continue

                # Not enough time has passed
                if now - sent_at < timedelta(days=delay_days):
                    continue

                # Check existing follow-up count for this tracker
                existing_resp = (
                    self.db.table(self.instances_table)
                    .select("id, follow_up_number, status")
                    .eq("tracker_id", tracker_id)
                    .order("follow_up_number", desc=True)
                    .limit(1)
                    .execute()
                )
                existing = existing_resp.data or []
                current_count = existing[0].get("follow_up_number", 0) if existing else 0

                if current_count >= max_follow_ups:
                    skipped.append({
                        "tracker_id": tracker_id,
                        "reason": f"Already at max follow-ups ({max_follow_ups})",
                    })
                    continue

                # Check if we already have a pending follow-up for this tracker
                pending_resp = (
                    self.db.table(self.instances_table)
                    .select("id")
                    .eq("tracker_id", tracker_id)
                    .eq("status", "PENDING")
                    .execute()
                )
                if pending_resp.data:
                    skipped.append({
                        "tracker_id": tracker_id,
                        "reason": "Already has a pending follow-up",
                    })
                    continue

                # All checks passed — generate the follow-up
                follow_up_number = current_count + 1
                scheduled_at = (sent_at + timedelta(days=delay_days * follow_up_number)).isoformat()

                if dry_run:
                    generated.append({
                        "tracker_id": tracker_id,
                        "email": email,
                        "company_name": se.get("company_name", ""),
                        "follow_up_number": follow_up_number,
                        "scheduled_at": scheduled_at,
                        "rule_id": rule["id"],
                        "rule_name": rule.get("name", ""),
                    })
                    continue

                # Generate follow-up email content
                company_name = se.get("company_name", "")
                original_subject = se.get("email_subject", "")

                # Fetch lead context for personalised follow-up
                lead = self.ingestion.fetch_lead_by_email(email)
                context = ""
                if lead:
                    context = lead.get("context") or lead.get("Context") or ""

                email_content = self.email_gen.follow_up(
                    company_name=company_name,
                    context=context,
                    recipient_email=email,
                    previous_subject=original_subject,
                    follow_up_number=follow_up_number,
                )

                # Insert follow-up instance
                now_iso = now.isoformat()
                instance = {
                    "id": str(uuid.uuid4()),
                    "rule_id": rule["id"],
                    "tracker_id": tracker_id,
                    "company_name": company_name,
                    "email": email,
                    "original_subject": original_subject,
                    "original_sent_at": sent_at_str,
                    "follow_up_number": follow_up_number,
                    "scheduled_at": scheduled_at,
                    "status": "PENDING",
                    "email_subject": email_content.get("subject", f"Re: {original_subject}"),
                    "email_body_preview": email_content.get("body_text", ""),
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
                self.db.table(self.instances_table).insert(instance).execute()
                generated.append({
                    "instance_id": instance["id"],
                    "tracker_id": tracker_id,
                    "email": email,
                    "company_name": company_name,
                    "follow_up_number": follow_up_number,
                })
                logger.info(
                    "Follow-up #%d generated for %s (%s)",
                    follow_up_number, company_name, email,
                )

        return {
            "generated": len(generated),
            "skipped": len(skipped),
            "details": generated,
            "skipped_details": skipped,
            "dry_run": dry_run,
        }
