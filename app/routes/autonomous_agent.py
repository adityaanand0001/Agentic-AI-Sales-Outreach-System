"""API routes for autonomous mailing agent control."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.deps.container import (
    get_autonomous_agent,
    get_agent_scheduler,
    get_gmail_service,
    get_mail_tracker,
)
from app.models.schemas import (
    AgentConfigUpdate,
    AgentStatusResponse,
    BatchRunResponse,
    SchedulerConfigUpdate,
    SchedulerStatusResponse,
)
from app.services.autonomous_agent import AutonomousMailingAgent
from app.services.gmail_oauth import GmailOAuthService
from app.services.mail_tracker import MailTrackerService
from app.services.scheduler import AgentScheduler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/autonomous-agent", tags=["autonomous-agent"])


# ── Agent Control ────────────────────────────────────────────────────────────

@router.get("/status", response_model=AgentStatusResponse)
async def get_agent_status(
    agent: AutonomousMailingAgent = Depends(get_autonomous_agent),
):
    """Get current status of the autonomous agent."""
    status = await agent.get_status()
    return AgentStatusResponse(**status)


@router.post("/run-batch", response_model=BatchRunResponse)
async def run_agent_batch(
    agent: AutonomousMailingAgent = Depends(get_autonomous_agent),
):
    """Run a single batch immediately (manual trigger)."""
    try:
        result = await agent.run_batch()
        return BatchRunResponse(
            batch_id=result.get("batch_id", "unknown"),
            status=result.get("status", "UNKNOWN"),
            summary=result.get("summary", {}),
            error=result.get("error"),
        )
    except Exception as e:
        logger.error("Failed to run batch: %s", e)
        raise HTTPException(500, f"Failed to run batch: {e}")


@router.post("/pause")
async def pause_agent(
    agent: AutonomousMailingAgent = Depends(get_autonomous_agent),
):
    """Pause the autonomous agent."""
    await agent.pause()
    return {"status": "PAUSED", "message": "Agent paused"}


@router.post("/resume")
async def resume_agent(
    agent: AutonomousMailingAgent = Depends(get_autonomous_agent),
):
    """Resume the autonomous agent."""
    await agent.resume()
    return {"status": "RUNNING", "message": "Agent resumed"}


@router.post("/config", response_model=AgentConfigUpdate)
async def update_agent_config(
    config: AgentConfigUpdate,
    agent: AutonomousMailingAgent = Depends(get_autonomous_agent),
):
    """Update agent configuration."""
    # For now, agent config is hardcoded in the class
    # In production, implement dynamic configuration
    return AgentConfigUpdate(
        auto_send_threshold=agent.auto_send_threshold,
        batch_size=agent.batch_size,
        processing_delay=agent.processing_delay,
        message="Configuration updated in memory (requires restart for persistence)",
    )


# ── Scheduler Control ────────────────────────────────────────────────────────

@router.get("/scheduler/status", response_model=SchedulerStatusResponse)
async def get_scheduler_status(
    scheduler: AgentScheduler = Depends(get_agent_scheduler),
):
    """Get current status of the agent scheduler."""
    status = await scheduler.get_status()
    return SchedulerStatusResponse(**status)


@router.post("/scheduler/start")
async def start_scheduler(
    scheduler: AgentScheduler = Depends(get_agent_scheduler),
):
    """Start the agent scheduler."""
    await scheduler.start()
    return {"status": "STARTED", "message": "Scheduler started"}


@router.post("/scheduler/stop")
async def stop_scheduler(
    scheduler: AgentScheduler = Depends(get_agent_scheduler),
):
    """Stop the agent scheduler."""
    await scheduler.stop()
    return {"status": "STOPPED", "message": "Scheduler stopped"}


@router.post("/scheduler/run-now", response_model=BatchRunResponse)
async def run_scheduler_batch_now(
    scheduler: AgentScheduler = Depends(get_agent_scheduler),
):
    """Run a scheduler batch immediately."""
    result = await scheduler.run_manual_batch()

    if "error" in result:
        raise HTTPException(400, result["error"])

    return BatchRunResponse(
        batch_id=result.get("batch_id", "unknown"),
        status=result.get("status", "STARTED"),
        message=result.get("message"),
    )


@router.post("/scheduler/config", response_model=SchedulerConfigUpdate)
async def update_scheduler_config(
    config: SchedulerConfigUpdate,
    scheduler: AgentScheduler = Depends(get_agent_scheduler),
):
    """Update scheduler configuration."""
    try:
        result = await scheduler.update_config(config.dict(exclude_unset=True))
        return SchedulerConfigUpdate(**result["current_config"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("Failed to update scheduler config: %s", e)
        raise HTTPException(500, f"Failed to update config: {e}")


# ── Queue Management ─────────────────────────────────────────────────────────

@router.get("/queue/stats")
async def get_queue_stats(
    agent: AutonomousMailingAgent = Depends(get_autonomous_agent),
):
    """Get processing queue statistics."""
    try:
        # Get counts by status
        resp = agent.db.table("processing_queue").select("status").execute()
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

        # Get human review queue count
        review_resp = agent.db.table("human_review_queue").select("id").eq("status", "PENDING").execute()
        pending_reviews = len(review_resp.data or [])

        # Get recent activity
        recent_resp = agent.db.table("processing_queue").select("*").order("created_at", desc=True).limit(10).execute()
        recent = recent_resp.data or []

        return {
            "processing_queue": counts,
            "human_review_queue": {
                "pending": pending_reviews,
                "total": len(review_resp.data or []),
            },
            "recent_activity": recent[:5],
        }

    except Exception as e:
        logger.error("Failed to get queue stats: %s", e)
        raise HTTPException(500, f"Failed to get queue stats: {e}")


@router.get("/human-review/pending")
async def get_pending_human_reviews(
    agent: AutonomousMailingAgent = Depends(get_autonomous_agent),
    limit: int = 50,
    offset: int = 0,
):
    """Get pending human review items."""
    try:
        resp = (
            agent.db.table("human_review_queue")
            .select("*, mail_agent_tracker(*)")
            .eq("status", "PENDING")
            .order("priority", desc=True)
            .order("created_at", desc=False)
            .limit(limit)
            .range(offset, offset + limit - 1)
            .execute()
        )

        return resp.data or []

    except Exception as e:
        logger.error("Failed to get pending reviews: %s", e)
        raise HTTPException(500, f"Failed to get pending reviews: {e}")


@router.post("/human-review/{review_id}/approve")
async def approve_human_review(
    review_id: str,
    agent: AutonomousMailingAgent = Depends(get_autonomous_agent),
    tracker: MailTrackerService = Depends(get_mail_tracker),
    gmail_service: GmailOAuthService = Depends(get_gmail_service),
):
    """Approve a human review item and send the email."""
    try:
        # Get review item
        resp = agent.db.table("human_review_queue").select("*").eq("id", review_id).limit(1).execute()
        reviews = resp.data or []

        if not reviews:
            raise HTTPException(404, "Review item not found")

        review = reviews[0]
        tracker_id = review.get("tracker_id")

        if not tracker_id:
            raise HTTPException(400, "Review item has no tracker ID")

        # Get tracker record
        record = tracker.get_record(tracker_id)
        if not record:
            raise HTTPException(404, "Tracker record not found")

        if record["status"] != "PENDING":
            raise HTTPException(400, f"Email is already {record['status']}")

        # Send email
        recipient = record["email"]
        subject = record["email_subject"]
        body_text = record["email_body_preview"]

        msg_id = gmail_service.safe_send_email(
            recipient=recipient,
            subject=subject,
            body_text=body_text,
        )

        # Update tracker
        tracker.update_status(
            tracker_id,
            "SENT",
            gmail_message_id=msg_id,
        )

        # Update review item
        agent.db.table("human_review_queue").update({
            "status": "APPROVED",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", review_id).execute()

        return {
            "status": "APPROVED",
            "tracker_id": tracker_id,
            "gmail_message_id": msg_id,
            "message": "Email sent successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to approve review %s: %s", review_id, e)
        raise HTTPException(500, f"Failed to approve review: {e}")


@router.post("/human-review/{review_id}/reject")
async def reject_human_review(
    review_id: str,
    reason: str = "",
    agent: AutonomousMailingAgent = Depends(get_autonomous_agent),
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Reject a human review item."""
    try:
        # Get review item
        resp = agent.db.table("human_review_queue").select("*").eq("id", review_id).limit(1).execute()
        reviews = resp.data or []

        if not reviews:
            raise HTTPException(404, "Review item not found")

        review = reviews[0]
        tracker_id = review.get("tracker_id")

        if not tracker_id:
            raise HTTPException(400, "Review item has no tracker ID")

        # Update tracker
        tracker.update_status(tracker_id, "REJECTED", error=reason or "Rejected by human reviewer")

        # Update review item
        agent.db.table("human_review_queue").update({
            "status": "REJECTED",
            "review_notes": reason,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", review_id).execute()

        return {
            "status": "REJECTED",
            "tracker_id": tracker_id,
            "message": "Email rejected",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to reject review %s: %s", review_id, e)
        raise HTTPException(500, f"Failed to reject review: {e}")


# ── Performance Metrics ──────────────────────────────────────────────────────

@router.get("/metrics/daily")
async def get_daily_metrics(
    agent: AutonomousMailingAgent = Depends(get_autonomous_agent),
    days: int = 7,
):
    """Get daily performance metrics."""
    try:
        from datetime import datetime, timedelta, timezone

        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days - 1)

        resp = (
            agent.db.table("performance_metrics")
            .select("*")
            .eq("metric_type", "DAILY")
            .gte("metric_date", start_date.isoformat())
            .lte("metric_date", end_date.isoformat())
            .order("metric_date", desc=True)
            .execute()
        )

        return resp.data or []

    except Exception as e:
        logger.error("Failed to get daily metrics: %s", e)
        raise HTTPException(500, f"Failed to get daily metrics: {e}")


@router.get("/metrics/summary")
async def get_metrics_summary(
    agent: AutonomousMailingAgent = Depends(get_autonomous_agent),
):
    """Get summary performance metrics."""
    try:
        # Get today's metrics
        today = datetime.now(timezone.utc).date().isoformat()

        resp = agent.db.table("performance_metrics").select("*").eq("metric_date", today).eq("metric_type", "DAILY").execute()
        today_metrics = resp.data[0] if resp.data else {}

        # Get total counts
        tracker_resp = agent.db.table("mail_agent_tracker").select("status").execute()
        tracker_rows = tracker_resp.data or []

        tracker_counts = {
            "total": len(tracker_rows),
            "PENDING": 0,
            "SENT": 0,
            "REJECTED": 0,
            "FAILED": 0,
        }

        for r in tracker_rows:
            status = r.get("status", "PENDING")
            if status in tracker_counts:
                tracker_counts[status] += 1

        return {
            "today": today_metrics,
            "tracker_totals": tracker_counts,
            "auto_send_rate": (
                today_metrics.get("auto_approved", 0) / max(1, today_metrics.get("emails_generated", 1))
                if today_metrics else 0
            ),
            "human_review_rate": (
                today_metrics.get("human_reviewed", 0) / max(1, today_metrics.get("emails_generated", 1))
                if today_metrics else 0
            ),
        }

    except Exception as e:
        logger.error("Failed to get metrics summary: %s", e)
        raise HTTPException(500, f"Failed to get metrics summary: {e}")