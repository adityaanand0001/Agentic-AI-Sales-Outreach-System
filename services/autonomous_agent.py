"""Autonomous Mailing Agent - Full AI-driven workflow."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from supabase import Client

from app.config.settings import get_settings
from app.services.email_generator import EmailGeneratorService
from app.services.gmail_oauth import GmailOAuthService
from app.services.ingestion import LeadIngestionService
from app.services.mail_tracker import MailTrackerService

logger = logging.getLogger(__name__)


class AutonomousMailingAgent:
    """Fully autonomous mailing agent with AI decision-making."""

    def __init__(
        self,
        db: Client,
        ingestion: LeadIngestionService,
        email_gen: EmailGeneratorService,
        tracker: MailTrackerService,
        gmail: GmailOAuthService,
    ) -> None:
        self.db = db
        self.ingestion = ingestion
        self.email_gen = email_gen
        self.tracker = tracker
        self.gmail = gmail
        self.settings = get_settings()

        # Configuration
        self.batch_size = self.settings.ingest_batch_size
        self.auto_send_threshold = 0.8  # 80% confidence for auto-send
        self.max_retries = 3
        self.processing_delay = 2.0  # seconds between leads

    # ── Main Orchestration ─────────────────────────────────────────────────────

    async def run_batch(self, batch_id: str | None = None) -> dict:
        """Run a full autonomous batch processing cycle."""
        batch_id = batch_id or f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        logger.info("Starting autonomous batch: %s", batch_id)

        try:
            # 1. Discover new leads
            leads = await self._discover_new_leads(batch_id)
            if not leads:
                logger.info("No new leads to process")
                return {"batch_id": batch_id, "status": "COMPLETED", "processed": 0}

            # 2. Prioritize leads
            prioritized = await self._prioritize_leads(leads, batch_id)

            # 3. Process each lead
            results = []
            for lead in prioritized:
                result = await self._process_single_lead(lead, batch_id)
                results.append(result)
                await asyncio.sleep(self.processing_delay)  # Rate limiting

            # 4. Generate summary
            summary = self._generate_batch_summary(batch_id, results)

            logger.info("Batch %s completed: %s", batch_id, summary)
            return {
                "batch_id": batch_id,
                "status": "COMPLETED",
                "summary": summary,
                "results": results,
            }

        except Exception as e:
            logger.error("Batch %s failed: %s", batch_id, e)
            return {
                "batch_id": batch_id,
                "status": "FAILED",
                "error": str(e),
            }

    # ── Phase 1: Discovery ────────────────────────────────────────────────────

    async def _discover_new_leads(self, batch_id: str) -> list[dict]:
        """Find new leads that haven't been processed yet."""
        # For now, fetch all leads (since no status column)
        # In production, you'd want to track processed leads
        leads = self.ingestion.fetch_pending_leads()

        # Create queue entries for each lead
        queue_entries = []
        for lead in leads:
            queue_entry = self._create_queue_entry(lead, batch_id)
            queue_entries.append(queue_entry)

        if queue_entries:
            # Bulk insert queue entries
            self.db.table("processing_queue").insert(queue_entries).execute()
            logger.info("Discovered %d new leads for batch %s", len(leads), batch_id)

        return leads

    def _create_queue_entry(self, lead: dict, batch_id: str) -> dict:
        """Create a processing queue entry for a lead."""
        now = datetime.now(timezone.utc).isoformat()
        return {
            "id": str(uuid.uuid4()),
            "batch_id": batch_id,
            "lead_id": lead.get("id"),
            "priority": 50,  # Default priority
            "status": "PENDING",
            "processing_stage": "NEW",
            "scheduled_for": now,
            "metadata": {
                "company_name": lead.get("name"),
                "email": lead.get("email"),
                "context_preview": (lead.get("context") or "")[:100],
            },
            "created_at": now,
            "updated_at": now,
        }

    # ── Phase 2: Prioritization ───────────────────────────────────────────────

    async def _prioritize_leads(self, leads: list[dict], batch_id: str) -> list[dict]:
        """Use AI to prioritize which leads to process first."""
        if not leads:
            return []

        # Simple prioritization for now:
        # 1. Leads with more context get higher priority
        # 2. Leads with company names get higher priority
        # In production, use AI for sophisticated prioritization

        prioritized = []
        for lead in leads:
            priority = self._calculate_priority_score(lead)
            lead["_priority"] = priority
            prioritized.append(lead)

        # Sort by priority (highest first)
        prioritized.sort(key=lambda x: x["_priority"], reverse=True)

        # Update queue with priorities
        for lead in prioritized:
            self.db.table("processing_queue").update({
                "priority": lead["_priority"],
                "processing_stage": "EVALUATED",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("lead_id", lead["id"]).execute()

        logger.info("Prioritized %d leads for batch %s", len(prioritized), batch_id)
        return prioritized

    def _calculate_priority_score(self, lead: dict) -> int:
        """Calculate priority score for a lead (0-100)."""
        score = 50  # Base score

        # Company name quality
        name = lead.get("name", "")
        if name and len(name) > 2:
            score += 10

        # Context length (more context = better)
        context = lead.get("context", "")
        if context:
            score += min(20, len(context) // 50)  # +1 for every 50 chars, max +20

        # Email quality
        email = lead.get("email", "")
        if email and "@" in email and "." in email:
            score += 10

        return min(100, max(1, score))

    # ── Phase 3: Processing ───────────────────────────────────────────────────

    async def _process_single_lead(self, lead: dict, batch_id: str) -> dict:
        """Process a single lead through the full pipeline."""
        lead_id = lead.get("id")
        queue_id = self._get_queue_id_for_lead(lead_id, batch_id)

        try:
            # Update status to PROCESSING
            self._update_queue_status(queue_id, "PROCESSING", "GENERATED")

            # Generate email
            company_name = lead.get("name") or "Unknown"
            context = lead.get("context") or ""
            recipient_email = lead.get("email") or ""

            if not recipient_email:
                raise ValueError("Lead has no email address")

            email_content = self.email_gen.generate(company_name, context, recipient_email)

            # Create tracker record
            tracker_record = self.tracker.create_record(
                company_name=company_name,
                email=recipient_email,
                subject=email_content["subject"],
                body_preview=email_content["body_text"],
                status="PENDING",
            )

            # Update queue with tracker ID
            self._update_queue_with_tracker(queue_id, tracker_record["id"])

            # AI quality check
            confidence, requires_human = await self._ai_quality_check(
                email_content, company_name, context
            )

            # Log AI decision
            self._log_ai_decision(
                queue_id=queue_id,
                tracker_id=tracker_record["id"],
                decision_type="QUALITY_CHECK",
                input_data={
                    "company_name": company_name,
                    "context_preview": context[:200],
                    "email_subject": email_content["subject"],
                    "email_body_preview": email_content["body_text"][:500],
                },
                output_data={
                    "confidence": confidence,
                    "requires_human": requires_human,
                    "decision": "HUMAN_REVIEW" if requires_human else "AUTO_APPROVE",
                },
                confidence=confidence,
            )

            # Update queue with AI decision
            self._update_queue_ai_decision(queue_id, confidence, requires_human)

            # Determine next action
            if not requires_human and confidence >= self.auto_send_threshold:
                # Auto-send
                result = await self._auto_send_email(tracker_record["id"], email_content)
                self._update_queue_status(queue_id, "COMPLETED", "SENT")
            elif requires_human:
                # Send to human review
                self._send_to_human_review(queue_id, tracker_record["id"], confidence)
                self._update_queue_status(queue_id, "COMPLETED", "REVIEW")
                result = {"action": "HUMAN_REVIEW", "tracker_id": tracker_record["id"]}
            else:
                # Low confidence, mark as completed but not sent
                self._update_queue_status(queue_id, "COMPLETED", "LOW_CONFIDENCE")
                result = {"action": "SKIPPED", "reason": "Low AI confidence"}

            return {
                "lead_id": lead_id,
                "tracker_id": tracker_record["id"],
                "company_name": company_name,
                "email": recipient_email,
                "confidence": confidence,
                "requires_human": requires_human,
                "result": result,
            }

        except Exception as e:
            logger.error("Failed to process lead %s: %s", lead_id, e)
            self._update_queue_status(queue_id, "FAILED", "ERROR", error=str(e))
            return {
                "lead_id": lead_id,
                "error": str(e),
                "result": {"action": "FAILED"},
            }

    # ── AI Decision Making ────────────────────────────────────────────────────

    async def _ai_quality_check(
        self, email_content: dict, company_name: str, context: str
    ) -> tuple[float, bool]:
        """Use AI to evaluate email quality and decide if human review needed."""
        # For now, use simple heuristics
        # In production, call LLM for sophisticated evaluation

        confidence = 0.7  # Base confidence

        # Check email length
        body_len = len(email_content.get("body_text", ""))
        if 100 <= body_len <= 500:
            confidence += 0.1
        elif body_len > 1000:
            confidence -= 0.2

        # Check subject
        subject = email_content.get("subject", "")
        if subject and len(subject) > 10:
            confidence += 0.1

        # Check for personalization
        if company_name.lower() in email_content.get("body_text", "").lower():
            confidence += 0.1

        # Determine if human review needed
        requires_human = confidence < self.auto_send_threshold

        return min(1.0, max(0.0, confidence)), requires_human

    # ── Auto-Send Logic ───────────────────────────────────────────────────────

    async def _auto_send_email(self, tracker_id: str, email_content: dict) -> dict:
        """Automatically send an approved email."""
        record = self.tracker.get_record(tracker_id)
        if not record:
            raise ValueError(f"Tracker record {tracker_id} not found")

        recipient = record["email"]
        subject = email_content["subject"]
        body_text = email_content["body_text"]

        try:
            msg_id = self.gmail.safe_send_email(
                recipient=recipient,
                subject=subject,
                body_text=body_text,
            )

            self.tracker.update_status(
                tracker_id,
                "SENT",
                gmail_message_id=msg_id,
            )

            # Log AI decision for auto-send
            self._log_ai_decision(
                tracker_id=tracker_id,
                decision_type="AUTO_APPROVAL",
                input_data={
                    "recipient": recipient,
                    "subject": subject,
                    "body_preview": body_text[:200],
                },
                output_data={
                    "decision": "AUTO_SEND",
                    "gmail_message_id": msg_id,
                },
                confidence=1.0,  # Full confidence for executed action
            )

            return {
                "action": "AUTO_SENT",
                "gmail_message_id": msg_id,
                "status": "SENT",
            }

        except Exception as e:
            logger.error("Auto-send failed for %s: %s", tracker_id, e)
            self.tracker.update_status(tracker_id, "FAILED", error=str(e))
            raise

    # ── Human Review Queue ────────────────────────────────────────────────────

    def _send_to_human_review(self, queue_id: str, tracker_id: str, confidence: float) -> None:
        """Add email to human review queue."""
        now = datetime.now(timezone.utc).isoformat()

        reason = "Low AI confidence"
        if confidence < 0.5:
            reason = "Very low confidence - needs human evaluation"
        elif confidence < 0.7:
            reason = "Moderate confidence - recommend review"

        review_entry = {
            "id": str(uuid.uuid4()),
            "queue_id": queue_id,
            "tracker_id": tracker_id,
            "reason": reason,
            "priority": int(100 - (confidence * 100)),  # Lower confidence = higher priority
            "status": "PENDING",
            "created_at": now,
            "updated_at": now,
        }

        self.db.table("human_review_queue").insert(review_entry).execute()
        logger.info("Sent tracker %s to human review: %s", tracker_id, reason)

    # ── Utility Methods ───────────────────────────────────────────────────────

    def _get_queue_id_for_lead(self, lead_id: str, batch_id: str) -> str:
        """Get queue ID for a lead in the current batch."""
        resp = self.db.table("processing_queue").select("id").eq("lead_id", lead_id).eq("batch_id", batch_id).limit(1).execute()
        rows = resp.data or []
        if not rows:
            raise ValueError(f"No queue entry found for lead {lead_id} in batch {batch_id}")
        return rows[0]["id"]

    def _update_queue_status(
        self, queue_id: str, status: str, stage: str, error: str = ""
    ) -> None:
        """Update queue entry status."""
        update_data = {
            "status": status,
            "processing_stage": stage,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if error:
            update_data["error"] = error

        self.db.table("processing_queue").update(update_data).eq("id", queue_id).execute()

    def _update_queue_with_tracker(self, queue_id: str, tracker_id: str) -> None:
        """Link queue entry to tracker record."""
        self.db.table("processing_queue").update({
            "tracker_id": tracker_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", queue_id).execute()

    def _update_queue_ai_decision(
        self, queue_id: str, confidence: float, requires_human: bool
    ) -> None:
        """Update queue with AI decision results."""
        self.db.table("processing_queue").update({
            "ai_confidence": confidence,
            "requires_human": requires_human,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", queue_id).execute()

    def _log_ai_decision(
        self,
        queue_id: str | None = None,
        tracker_id: str | None = None,
        decision_type: str = "UNKNOWN",
        input_data: dict | None = None,
        output_data: dict | None = None,
        confidence: float = 0.0,
    ) -> None:
        """Log an AI decision to the database."""
        now = datetime.now(timezone.utc).isoformat()

        decision_entry = {
            "id": str(uuid.uuid4()),
            "queue_id": queue_id,
            "tracker_id": tracker_id,
            "decision_type": decision_type,
            "input_data": input_data or {},
            "output_data": output_data or {},
            "confidence": confidence,
            "model_used": self.settings.llm_model,
            "created_at": now,
        }

        self.db.table("ai_decisions").insert(decision_entry).execute()

    def _generate_batch_summary(self, batch_id: str, results: list[dict]) -> dict:
        """Generate summary statistics for a batch."""
        total = len(results)
        successful = sum(1 for r in results if "error" not in r)
        failed = total - successful
        auto_sent = sum(1 for r in results if r.get("result", {}).get("action") == "AUTO_SENT")
        human_review = sum(1 for r in results if r.get("result", {}).get("action") == "HUMAN_REVIEW")
        skipped = sum(1 for r in results if r.get("result", {}).get("action") == "SKIPPED")

        # Calculate average confidence
        confidences = [r.get("confidence", 0) for r in results if "confidence" in r]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0

        return {
            "total_leads": total,
            "successful": successful,
            "failed": failed,
            "auto_sent": auto_sent,
            "human_review": human_review,
            "skipped": skipped,
            "avg_confidence": round(avg_confidence, 3),
        }

    # ── Monitoring & Control ──────────────────────────────────────────────────

    async def get_status(self) -> dict:
        """Get current agent status."""
        # Count queue items by status
        resp = self.db.table("processing_queue").select("status").execute()
        rows = resp.data or []

        counts = {"total": len(rows), "PENDING": 0, "PROCESSING": 0, "COMPLETED": 0, "FAILED": 0}
        for r in rows:
            status = r.get("status", "PENDING")
            if status in counts:
                counts[status] += 1

        # Get human review queue size
        review_resp = self.db.table("human_review_queue").select("id").eq("status", "PENDING").execute()
        pending_reviews = len(review_resp.data or [])

        return {
            "agent_status": "RUNNING",
            "queue_status": counts,
            "pending_human_reviews": pending_reviews,
            "auto_send_threshold": self.auto_send_threshold,
            "batch_size": self.batch_size,
        }

    async def pause(self) -> None:
        """Pause the agent (placeholder for future implementation)."""
        logger.info("Agent pause requested")
        # In production, implement proper pause/resume logic

    async def resume(self) -> None:
        """Resume the agent (placeholder for future implementation)."""
        logger.info("Agent resume requested")