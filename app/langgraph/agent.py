"""LangGraph agent service for autonomous mailing."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langgraph.graph import StateGraph
from supabase import Client

from app.config.settings import get_settings
from app.services.email_generator import EmailGeneratorService
from app.services.gmail_oauth import GmailOAuthService
from app.services.ingestion import LeadIngestionService
from app.services.mail_tracker import MailTrackerService
from app.langgraph.workflow import build_mailing_workflow

logger = logging.getLogger(__name__)


class LangGraphAgentService:
    """LangGraph-powered autonomous mailing agent."""

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

        # Build the workflow
        self.workflow = build_mailing_workflow(db, ingestion, email_gen, tracker, gmail)
        self.compiled_workflow = self.workflow.compile()

        # Configuration
        self.batch_size = self.settings.ingest_batch_size
        self.auto_send_threshold = self.settings.auto_send_threshold
        self.max_retries = 3
        self.processing_delay = 2.0  # seconds between leads

    async def process_single_lead(self, lead_id: str, batch_id: str | None = None) -> Dict[str, Any]:
        """Process a single lead through the LangGraph workflow."""
        batch_id = batch_id or f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        logger.info(f"Processing lead {lead_id} in batch {batch_id}")

        try:
            # Mark as PROCESSING in the queue immediately
            self.db.table("processing_queue").update({
                "status": "PROCESSING",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).eq("lead_id", lead_id).execute()

            # Prepare initial state
            initial_state = {
                "lead_id": lead_id,
                "batch_id": batch_id,
                "processing_stage": "STARTED",
                "llm_context": [],
            }

            # Execute workflow
            result = await self.compiled_workflow.ainvoke(initial_state)

            # Extract result
            final_state = result.get("__end__", result)

            # Record result in database
            self._record_processing_result(lead_id, batch_id, final_state)

            return {
                "lead_id": lead_id,
                "batch_id": batch_id,
                "status": "COMPLETED",
                "result": final_state,
            }

        except Exception as e:
            logger.error(f"Failed to process lead {lead_id}: {e}")
            return {
                "lead_id": lead_id,
                "batch_id": batch_id,
                "status": "FAILED",
                "error": str(e),
            }

    async def process_batch(self, lead_ids: List[str], batch_id: str | None = None) -> Dict[str, Any]:
        """Process a batch of leads through the LangGraph workflow."""
        batch_id = batch_id or f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        logger.info(f"Processing batch {batch_id} with {len(lead_ids)} leads")

        results = []
        for i, lead_id in enumerate(lead_ids):
            try:
                result = await self.process_single_lead(lead_id, batch_id)
                results.append(result)

                # Rate limiting
                if i < len(lead_ids) - 1:
                    await asyncio.sleep(self.processing_delay)

            except Exception as e:
                logger.error(f"Failed to process lead {lead_id} in batch {batch_id}: {e}")
                results.append({
                    "lead_id": lead_id,
                    "batch_id": batch_id,
                    "status": "FAILED",
                    "error": str(e),
                })

        # Generate batch summary
        summary = self._generate_batch_summary(batch_id, results)

        return {
            "batch_id": batch_id,
            "status": "COMPLETED",
            "summary": summary,
            "results": results,
            "total_leads": len(lead_ids),
            "successful": len([r for r in results if r.get("status") == "COMPLETED"]),
            "failed": len([r for r in results if r.get("status") == "FAILED"]),
        }

    async def run_autonomous_batch(self, batch_id: str | None = None) -> Dict[str, Any]:
        """Run a full autonomous batch processing cycle."""
        batch_id = batch_id or f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        logger.info(f"Starting autonomous batch: {batch_id}")

        try:
            # 0. Check Daily Quota (Safety first)
            if not self.gmail.check_daily_quota(self.db):
                logger.error("Daily email quota exceeded. Aborting batch.")
                return {"batch_id": batch_id, "status": "FAILED", "error": "Daily quota exceeded"}

            # 1. Self-Healing: Cleanup stale leads from previous crashed runs
            cleanup_resp = self.db.rpc('cleanup_stale_leads', {'p_timeout_minutes': 30}).execute()
            stale_count = cleanup_resp.data or 0
            if stale_count > 0:
                logger.info(f"Self-healing: Recovered {stale_count} stale leads from the queue")

            # 1. Discover new leads
            leads = await self.discover_new_leads(batch_id)
            if not leads:
                logger.info("No new leads to process")
                return {"batch_id": batch_id, "status": "COMPLETED", "processed": 0}

            # 2. Prioritize leads
            prioritized = await self._prioritize_leads(leads, batch_id)

            # 3. Process each lead
            lead_ids = [lead.get("id") for lead in prioritized if lead.get("id")]
            batch_result = await self.process_batch(lead_ids, batch_id)

            logger.info(f"Batch {batch_id} completed: {batch_result['summary']}")
            return batch_result

        except Exception as e:
            logger.error(f"Batch {batch_id} failed: {e}")
            return {
                "batch_id": batch_id,
                "status": "FAILED",
                "error": str(e),
            }

    async def run_autonomous_batch_with_events(self, queue: asyncio.Queue, batch_id: str | None = None):
        """Run batch with real-time SSE events pushed to queue."""
        batch_id = batch_id or f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        try:
            # Phase 1: Discover
            await queue.put({"type": "PHASE", "phase": "discover", "status": "active"})
            leads = await self.discover_new_leads(batch_id)
            if not leads:
                await queue.put({"type": "PHASE", "phase": "discover", "status": "completed", "count": 0})
                await queue.put({"type": "DONE", "total_leads": 0})
                return
            await queue.put({
                "type": "PHASE", "phase": "discover", "status": "completed",
                "count": len(leads),
                "leads": [{"name": l.get("name"), "email": l.get("email")} for l in leads[:10]]
            })

            # Phase 2: Prioritize
            await queue.put({"type": "PHASE", "phase": "prioritize", "status": "active"})
            prioritized = await self._prioritize_leads(leads, batch_id)
            await queue.put({
                "type": "PHASE", "phase": "prioritize", "status": "completed",
                "leads": [
                    {"name": l.get("name"), "email": l.get("email"), "score": l.get("_priority", 50) / 100}
                    for l in prioritized[:10]
                ]
            })

            # Phase 3: Process each lead through the compiled workflow
            total = len(prioritized)
            for i, lead in enumerate(prioritized):
                lead_id = lead.get("id")
                lead_name = lead.get("name", "Unknown")
                lead_email = lead.get("email", "")

                await queue.put({
                    "type": "LEAD_START", "index": i + 1, "total": total,
                    "name": lead_name, "email": lead_email
                })

                result = await self.process_single_lead(lead_id, batch_id)
                final = result.get("result", {}) if isinstance(result.get("result"), dict) else {}

                await queue.put({
                    "type": "LEAD_RESULT", "index": i + 1, "total": total,
                    "name": lead_name, "email": lead_email,
                    "status": result.get("status", "UNKNOWN"),
                    "action": final.get("action_taken"),
                    "confidence": final.get("ai_confidence", 0),
                    "subject": final.get("email_subject", ""),
                    "body_preview": final.get("email_body", ""),
                })

                if i < total - 1:
                    # Human-like jitter: delay between 1.5 and 4 seconds
                    import random
                    jitter_delay = random.uniform(1.5, 4.0)
                    await asyncio.sleep(jitter_delay)

            await queue.put({"type": "DONE", "total_leads": total})

        except Exception as e:
            logger.error(f"Streaming batch failed: {e}")
            await queue.put({"type": "ERROR", "message": str(e)})

    async def discover_new_leads(self, batch_id: str) -> List[Dict[str, Any]]:
        """Find new leads atomically using a database-side claim transaction."""
        target_batch_size = self.settings.batch_size
        
        logger.info(f"Discovering and claiming up to {target_batch_size} leads for batch {batch_id}")
        
        try:
            # Atomic claim via Postgres RPC
            resp = self.db.rpc('discover_and_claim_leads', {
                'p_batch_id': batch_id,
                'p_limit': target_batch_size
            }).execute()

            new_leads = resp.data or []
            
            if not new_leads:
                logger.info(f"No new leads available for claiming.")
                return []

            logger.info(f"Atomically claimed {len(new_leads)} new leads for batch {batch_id}")
            return new_leads

        except Exception as e:
            logger.error(f"Atomic lead discovery failed: {e}")
            # Fallback to empty list to avoid duplicate processing on error
            return []

    def _create_queue_entry(self, lead: Dict[str, Any], batch_id: str) -> Dict[str, Any]:
        """Create a processing queue entry for a lead."""
        now = datetime.now(timezone.utc).isoformat()
        return {
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

    async def _prioritize_leads(self, leads: List[Dict[str, Any]], batch_id: str) -> List[Dict[str, Any]]:
        """Prioritize leads for processing."""
        if not leads:
            return []

        # AI-driven prioritization
        prioritized = []
        for lead in leads:
            # Get AI score (0.0 to 1.0)
            ai_score = self.email_gen.prioritize(lead.get("name", "Unknown"), lead.get("context", ""))
            
            # Simple boost for email presence (0.05)
            bonus = 0.05 if lead.get("email") and "@" in lead.get("email") else 0
                
            final_score = min(1.0, ai_score + bonus)
            lead["_priority"] = int(final_score * 100)
            prioritized.append(lead)

        # Sort by priority (highest first)
        prioritized.sort(key=lambda x: x["_priority"], reverse=True)

        # Update queue with priorities
        for lead in prioritized:
            self.db.table("processing_queue").update({
                "priority": lead["_priority"],
                "processing_stage": "PRIORITIZED",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("lead_id", lead["id"]).execute()

        logger.info(f"Prioritized {len(prioritized)} leads for batch {batch_id}")

        return prioritized


    def _record_processing_result(self, lead_id: str, batch_id: str, final_state: Dict[str, Any]) -> None:
        """Record processing result in database."""
        try:
            # Update processing queue
            update_data = {
                "status": "COMPLETED",
                "processing_stage": final_state.get("processing_stage", "COMPLETED"),
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            if "tracker_id" in final_state:
                update_data["tracker_id"] = final_state["tracker_id"]

            if "ai_confidence" in final_state:
                update_data["ai_confidence"] = final_state["ai_confidence"]
                update_data["requires_human"] = final_state.get("requires_human", False)

            if "error" in final_state:
                update_data["error"] = final_state["error"]
                update_data["status"] = "FAILED"

            self.db.table("processing_queue").update(update_data).eq("lead_id", lead_id).eq("batch_id", batch_id).execute()

        except Exception as e:
            logger.error(f"Failed to record processing result for lead {lead_id}: {e}")

    def _generate_batch_summary(self, batch_id: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate summary statistics for a batch."""
        total = len(results)
        successful = sum(1 for r in results if r.get("status") == "COMPLETED")
        failed = total - successful

        # Extract actions from results
        actions = []
        for r in results:
            if r.get("status") == "COMPLETED" and "result" in r:
                actions.append(r["result"].get("action_taken"))

        auto_sent = actions.count("AUTO_SENT")
        human_review = actions.count("HUMAN_REVIEW")
        skipped = actions.count("SKIPPED")

        # Calculate average confidence
        confidences = []
        for r in results:
            if r.get("status") == "COMPLETED" and "result" in r:
                conf = r["result"].get("ai_confidence")
                if conf is not None:
                    confidences.append(conf)

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

    async def get_workflow_status(self) -> Dict[str, Any]:
        """Get current workflow status and statistics."""
        try:
            # Get queue statistics
            resp = self.db.table("processing_queue").select("status").execute()
            rows = resp.data or []

            counts = {
                "total": len(rows),
                "PENDING": 0,
                "PROCESSING": 0,
                "COMPLETED": 0,
                "FAILED": 0,
            }

            for r in rows:
                status = r.get("status", "PENDING")
                if status in counts:
                    counts[status] += 1

            # Get workflow execution stats
            ai_resp = self.db.table("ai_decisions").select("decision_type", "confidence").limit(100).execute()
            ai_decisions = ai_resp.data or []

            decision_types = {}
            avg_confidence = 0
            if ai_decisions:
                for d in ai_decisions:
                    dt = d.get("decision_type", "UNKNOWN")
                    decision_types[dt] = decision_types.get(dt, 0) + 1

                confidences = [d.get("confidence", 0) for d in ai_decisions if d.get("confidence")]
                avg_confidence = sum(confidences) / len(confidences) if confidences else 0

            return {
                "workflow_status": "ACTIVE",
                "queue_status": counts,
                "ai_decisions": decision_types,
                "avg_ai_confidence": round(avg_confidence, 3),
                "total_ai_decisions": len(ai_decisions),
                "workflow_version": "1.0.0",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to get workflow status: {e}")
            return {
                "workflow_status": "ERROR",
                "error": str(e),
            }

    def visualize_workflow(self, output_path: str | None = None) -> str:
        """Generate a visualization of the workflow with active node highlighting."""
        try:
            # Get current active stage from queue
            active_stage = "Start"
            resp = self.db.table("processing_queue").select("processing_stage").eq("status", "PROCESSING").limit(1).execute()
            if resp.data:
                active_stage = resp.data[0].get("processing_stage", "Start")

            # Map DB stages to Mermaid nodes
            stage_map = {
                "NEW": "Discover",
                "PRIORITIZED": "Prioritize",
                "GENERATING": "Generate",
                "QUALITY_CHECK": "Quality",
                "DECISION": "Decision",
                "COMPLETED": "End"
            }
            highlight_node = stage_map.get(active_stage, "Start")

            mermaid_diagram = f"""graph TD
    Start[Start] --> Discover[Discover Leads]
    Discover --> Prioritize[Prioritize Lead]
    Prioritize --> Generate[Generate Email]

    Generate --> Quality[Quality Check]
    Quality --> Decision[Make Decision]

    Decision -->|Auto-send| Complete[Complete]
    Decision -->|Human Review| Complete
    Decision -->|Skip| Complete

    Complete --> End[End]

    style Start fill:#f9f9f9,stroke:#333
    style End fill:#f9f9f9,stroke:#333
    style {highlight_node} fill:#2563eb,stroke:#2563eb,color:#fff,stroke-width:4px
"""

            if output_path:
                # Save to file
                with open(output_path, 'w') as f:
                    f.write(mermaid_diagram)

            return mermaid_diagram

        except Exception as e:
            logger.error(f"Failed to generate workflow visualization: {e}")
            return f"Error generating visualization: {e}"

    async def get_batch_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get summary history of recent batches."""
        try:
            # Query unique batch IDs from processing_queue
            # Since Supabase JS client doesn't support easy 'DISTINCT' or 'GROUP BY', 
            # we fetch recent entries and group in memory, or use a RPC if available.
            # For now, let's fetch the last 100 queue entries.
            resp = self.db.table("processing_queue").select("*").order("created_at", desc=True).limit(200).execute()
            entries = resp.data or []
            
            batches = {}
            for e in entries:
                bid = e.get("batch_id")
                if bid not in batches:
                    batches[bid] = {
                        "batch_id": bid,
                        "total_leads": 0,
                        "completed": 0,
                        "failed": 0,
                        "auto_sent": 0,
                        "human_review": 0,
                        "avg_confidence": 0,
                        "created_at": e.get("created_at")
                    }
                
                b = batches[bid]
                b["total_leads"] += 1
                if e.get("status") == "COMPLETED":
                    b["completed"] += 1
                elif e.get("status") == "FAILED":
                    b["failed"] += 1
                
                # Check for AI decisions associated with this lead
                # This is a bit expensive in a loop, in production use a view
            
            # Sort batches by created_at
            sorted_batches = sorted(batches.values(), key=lambda x: x["created_at"], reverse=True)
            return sorted_batches[:limit]
            
        except Exception as e:
            logger.error(f"Failed to get batch history: {e}")
            return []

    async def get_execution_logs(
        self, 
        tracker_id: Optional[str] = None, 
        batch_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Fetch audit logs of AI decisions."""
        try:
            query = self.db.table("ai_decisions").select("*").order("created_at", desc=True).limit(limit)
            
            if tracker_id:
                query = query.eq("tracker_id", tracker_id)
            # If we had a batch_id in ai_decisions, we'd filter by it too.
            # But we can join with processing_queue if needed.
            
            resp = query.execute()
            return resp.data or []
        except Exception as e:
            logger.error(f"Failed to get execution logs: {e}")
            return []