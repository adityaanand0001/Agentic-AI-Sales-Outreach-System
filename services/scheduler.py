"""Scheduler for autonomous agent runs."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.config.settings import get_settings
from app.services.autonomous_agent import AutonomousMailingAgent

logger = logging.getLogger(__name__)


class AgentScheduler:
    """Schedules and manages autonomous agent runs."""

    def __init__(
        self,
        agent: AutonomousMailingAgent,
        run_interval_minutes: int = 60,  # Run every hour
        max_concurrent_batches: int = 1,
    ) -> None:
        self.agent = agent
        self.run_interval = run_interval_minutes * 60  # Convert to seconds
        self.max_concurrent = max_concurrent_batches
        self.settings = get_settings()

        # State
        self.is_running = False
        self.current_task: asyncio.Task | None = None
        self.active_batches: dict[str, asyncio.Task] = {}
        self.run_history: list[dict] = []

    async def start(self) -> None:
        """Start the scheduler."""
        if self.is_running:
            logger.warning("Scheduler already running")
            return

        self.is_running = True
        logger.info("Starting agent scheduler (interval: %d minutes)", self.run_interval // 60)

        # Run initial batch immediately
        asyncio.create_task(self._run_scheduled_batch())

        # Start the scheduling loop
        self.current_task = asyncio.create_task(self._scheduler_loop())

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if not self.is_running:
            return

        logger.info("Stopping agent scheduler")
        self.is_running = False

        if self.current_task:
            self.current_task.cancel()
            try:
                await self.current_task
            except asyncio.CancelledError:
                pass

        # Wait for active batches to complete
        if self.active_batches:
            logger.info("Waiting for %d active batches to complete", len(self.active_batches))
            await asyncio.gather(*self.active_batches.values(), return_exceptions=True)

        logger.info("Scheduler stopped")

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop."""
        try:
            while self.is_running:
                await asyncio.sleep(self.run_interval)

                if self.is_running:
                    # Check if we can start a new batch
                    if len(self.active_batches) < self.max_concurrent:
                        asyncio.create_task(self._run_scheduled_batch())
                    else:
                        logger.warning(
                            "Max concurrent batches reached (%d), skipping scheduled run",
                            self.max_concurrent,
                        )

        except asyncio.CancelledError:
            logger.info("Scheduler loop cancelled")
            raise
        except Exception as e:
            logger.error("Scheduler loop error: %s", e)
            self.is_running = False

    async def _run_scheduled_batch(self) -> None:
        """Run a scheduled batch."""
        batch_id = f"scheduled_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        if batch_id in self.active_batches:
            logger.warning("Batch %s already running", batch_id)
            return

        logger.info("Starting scheduled batch: %s", batch_id)

        # Create and track the batch task
        task = asyncio.create_task(self._execute_batch(batch_id))
        self.active_batches[batch_id] = task

        try:
            await task
        finally:
            # Remove from active batches
            self.active_batches.pop(batch_id, None)

    async def _execute_batch(self, batch_id: str) -> None:
        """Execute a batch and handle results."""
        start_time = datetime.now(timezone.utc)

        try:
            result = await self.agent.run_batch(batch_id)

            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()

            # Record in history
            history_entry = {
                "batch_id": batch_id,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": duration,
                "result": result,
                "status": result.get("status", "UNKNOWN"),
            }

            self.run_history.append(history_entry)
            self.run_history = self.run_history[-100:]  # Keep last 100 entries

            logger.info(
                "Batch %s completed in %.1f seconds: %s",
                batch_id,
                duration,
                result.get("status"),
            )

            # Log performance metrics
            await self._log_performance_metrics(batch_id, result, duration)

        except Exception as e:
            logger.error("Batch %s failed: %s", batch_id, e)

            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()

            history_entry = {
                "batch_id": batch_id,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": duration,
                "error": str(e),
                "status": "FAILED",
            }

            self.run_history.append(history_entry)
            self.run_history = self.run_history[-100:]

    async def _log_performance_metrics(
        self, batch_id: str, result: dict, duration: float
    ) -> None:
        """Log performance metrics to database."""
        try:
            summary = result.get("summary", {})
            today = datetime.now(timezone.utc).date().isoformat()

            # Check if today's metrics already exist
            resp = self.agent.db.table("performance_metrics").select("*").eq("metric_date", today).eq("metric_type", "DAILY").execute()
            existing = resp.data or []

            if existing:
                # Update existing entry
                existing_id = existing[0]["id"]
                self.agent.db.table("performance_metrics").update({
                    "leads_processed": existing[0].get("leads_processed", 0) + summary.get("total_leads", 0),
                    "emails_generated": existing[0].get("emails_generated", 0) + summary.get("successful", 0),
                    "emails_sent": existing[0].get("emails_sent", 0) + summary.get("auto_sent", 0),
                    "auto_approved": existing[0].get("auto_approved", 0) + summary.get("auto_sent", 0),
                    "human_reviewed": existing[0].get("human_reviewed", 0) + summary.get("human_review", 0),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", existing_id).execute()
            else:
                # Create new entry
                metrics_entry = {
                    "id": str(uuid.uuid4()),
                    "metric_date": today,
                    "metric_type": "DAILY",
                    "leads_processed": summary.get("total_leads", 0),
                    "emails_generated": summary.get("successful", 0),
                    "emails_sent": summary.get("auto_sent", 0),
                    "auto_approved": summary.get("auto_sent", 0),
                    "human_reviewed": summary.get("human_review", 0),
                    "avg_confidence": summary.get("avg_confidence", 0),
                    "avg_processing_time": duration / max(1, summary.get("total_leads", 1)),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                self.agent.db.table("performance_metrics").insert(metrics_entry).execute()

        except Exception as e:
            logger.error("Failed to log performance metrics: %s", e)

    # ── Control & Monitoring ──────────────────────────────────────────────────

    async def get_status(self) -> dict:
        """Get scheduler status."""
        return {
            "is_running": self.is_running,
            "run_interval_minutes": self.run_interval // 60,
            "max_concurrent_batches": self.max_concurrent,
            "active_batches": list(self.active_batches.keys()),
            "active_batch_count": len(self.active_batches),
            "total_runs": len(self.run_history),
            "recent_runs": self.run_history[-5:] if self.run_history else [],
        }

    async def run_manual_batch(self) -> dict:
        """Run a manual batch immediately."""
        if not self.is_running:
            return {"error": "Scheduler not running"}

        batch_id = f"manual_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        if len(self.active_batches) >= self.max_concurrent:
            return {"error": "Max concurrent batches reached", "batch_id": batch_id}

        # Start manual batch
        task = asyncio.create_task(self._execute_batch(batch_id))
        self.active_batches[batch_id] = task

        # Don't wait for completion
        asyncio.create_task(self._track_manual_batch(batch_id, task))

        return {
            "batch_id": batch_id,
            "status": "STARTED",
            "message": f"Manual batch {batch_id} started",
        }

    async def _track_manual_batch(self, batch_id: str, task: asyncio.Task) -> None:
        """Track a manual batch and clean up when done."""
        try:
            await task
        finally:
            self.active_batches.pop(batch_id, None)

    async def update_config(self, config: dict) -> dict:
        """Update scheduler configuration."""
        updated = {}

        if "run_interval_minutes" in config:
            new_interval = config["run_interval_minutes"]
            if 1 <= new_interval <= 1440:  # 1 minute to 24 hours
                self.run_interval = new_interval * 60
                updated["run_interval_minutes"] = new_interval
            else:
                raise ValueError("Interval must be between 1 and 1440 minutes")

        if "max_concurrent_batches" in config:
            new_max = config["max_concurrent_batches"]
            if 1 <= new_max <= 10:
                self.max_concurrent = new_max
                updated["max_concurrent_batches"] = new_max
            else:
                raise ValueError("Max concurrent batches must be between 1 and 10")

        return {
            "status": "UPDATED",
            "updated_config": updated,
            "current_config": {
                "run_interval_minutes": self.run_interval // 60,
                "max_concurrent_batches": self.max_concurrent,
            },
        }