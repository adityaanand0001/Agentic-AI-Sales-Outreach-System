"""API routes for the Follow-up / Re-engagement Engine."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from app.config.database import get_supabase
from app.deps.container import (
    get_email_generator,
    get_gmail_service,
    get_lead_ingestion,
    get_mail_tracker,
)
from app.models.schemas import (
    FollowUpRuleCreate,
    FollowUpRuleUpdate,
    FollowUpRuleResponse,
    FollowUpInstance,
)
from app.services.email_generator import EmailGeneratorService
from app.services.follow_up import FollowUpService
from app.services.gmail_oauth import GmailOAuthService
from app.services.ingestion import LeadIngestionService
from app.services.mail_tracker import MailTrackerService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/follow-ups", tags=["follow-ups"])


# ── Dependency ────────────────────────────────────────────────────────────


def get_follow_up_service(
    db: Client = Depends(get_supabase),
    tracker: MailTrackerService = Depends(get_mail_tracker),
    ingestion: LeadIngestionService = Depends(get_lead_ingestion),
    email_gen: EmailGeneratorService = Depends(get_email_generator),
) -> FollowUpService:
    return FollowUpService(db, tracker, ingestion, email_gen)


# ── Rules CRUD ────────────────────────────────────────────────────────────


@router.get("/rules", response_model=list[FollowUpRuleResponse])
def list_rules(
    service: FollowUpService = Depends(get_follow_up_service),
):
    """List all follow-up rules."""
    return service.list_rules()


@router.get("/rules/{rule_id}", response_model=FollowUpRuleResponse)
def get_rule(
    rule_id: str,
    service: FollowUpService = Depends(get_follow_up_service),
):
    rule = service.get_rule(rule_id)
    if not rule:
        raise HTTPException(404, "Follow-up rule not found")
    return rule


@router.post("/rules", response_model=FollowUpRuleResponse)
def create_rule(
    req: FollowUpRuleCreate,
    service: FollowUpService = Depends(get_follow_up_service),
):
    """Create a new follow-up rule."""
    if req.delay_days < 1:
        raise HTTPException(400, "delay_days must be at least 1")
    if req.max_follow_ups < 1:
        raise HTTPException(400, "max_follow_ups must be at least 1")
    return service.create_rule(
        name=req.name,
        delay_days=req.delay_days,
        max_follow_ups=req.max_follow_ups,
    )


@router.patch("/rules/{rule_id}", response_model=FollowUpRuleResponse)
def update_rule(
    rule_id: str,
    req: FollowUpRuleUpdate,
    service: FollowUpService = Depends(get_follow_up_service),
):
    """Update a follow-up rule."""
    existing = service.get_rule(rule_id)
    if not existing:
        raise HTTPException(404, "Follow-up rule not found")

    updates = {}
    if req.name is not None:
        updates["name"] = req.name
    if req.delay_days is not None:
        if req.delay_days < 1:
            raise HTTPException(400, "delay_days must be at least 1")
        updates["delay_days"] = req.delay_days
    if req.max_follow_ups is not None:
        if req.max_follow_ups < 1:
            raise HTTPException(400, "max_follow_ups must be at least 1")
        updates["max_follow_ups"] = req.max_follow_ups
    if req.is_active is not None:
        updates["is_active"] = req.is_active

    updated = service.update_rule(rule_id, **updates)
    if not updated:
        raise HTTPException(500, "Failed to update rule")
    return updated


@router.delete("/rules/{rule_id}")
def delete_rule(
    rule_id: str,
    service: FollowUpService = Depends(get_follow_up_service),
):
    """Delete a follow-up rule."""
    existing = service.get_rule(rule_id)
    if not existing:
        raise HTTPException(404, "Follow-up rule not found")
    service.delete_rule(rule_id)
    return {"message": "Rule deleted"}


# ── Follow-up instances ────────────────────────────────────────────────────


@router.get("/pending", response_model=list[FollowUpInstance])
def list_pending(
    limit: int = 100,
    offset: int = 0,
    service: FollowUpService = Depends(get_follow_up_service),
):
    """List all pending follow-up emails ready for review."""
    return service.list_pending_follow_ups(limit=limit, offset=offset)


@router.get("/list", response_model=list[FollowUpInstance])
def list_all(
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    service: FollowUpService = Depends(get_follow_up_service),
):
    """List all follow-up instances, optionally filtered by status."""
    return service.list_follow_ups(status=status, limit=limit, offset=offset)


@router.get("/{instance_id}", response_model=FollowUpInstance)
def get_follow_up(
    instance_id: str,
    service: FollowUpService = Depends(get_follow_up_service),
):
    instance = service.get_follow_up(instance_id)
    if not instance:
        raise HTTPException(404, "Follow-up instance not found")
    return instance


# ── Actions ────────────────────────────────────────────────────────────────


@router.post("/generate")
def generate_follow_ups(
    rule_id: str | None = None,
    dry_run: bool = False,
    service: FollowUpService = Depends(get_follow_up_service),
):
    """
    Scan sent emails and generate follow-up instances for unreplied leads.

    - rule_id: Optional — apply only this rule. If omitted, applies all active rules.
    - dry_run: If true, reports what would be generated without inserting records.
    """
    try:
        result = service.generate_follow_ups(rule_id=rule_id, dry_run=dry_run)
        return result
    except Exception as e:
        logger.error("Follow-up generation failed: %s", e)
        raise HTTPException(500, f"Failed to generate follow-ups: {e}")


@router.post("/{instance_id}/approve")
def approve_follow_up(
    instance_id: str,
    service: FollowUpService = Depends(get_follow_up_service),
    gmail_service: GmailOAuthService = Depends(get_gmail_service),
):
    """Approve and send a pending follow-up email via Gmail."""
    result = service.approve_follow_up(instance_id, gmail_service)
    if not result:
        raise HTTPException(404, "Follow-up instance not found or already processed")
    if result["status"] == "FAILED":
        raise HTTPException(500, f"Failed to send: {result.get('error', 'unknown error')}")
    return {
        "instance_id": instance_id,
        "status": result["status"],
        "gmail_message_id": result.get("gmail_message_id", ""),
    }


@router.post("/{instance_id}/skip")
def skip_follow_up(
    instance_id: str,
    service: FollowUpService = Depends(get_follow_up_service),
):
    """Skip a pending follow-up (won't be sent)."""
    instance = service.get_follow_up(instance_id)
    if not instance:
        raise HTTPException(404, "Follow-up instance not found")
    if instance["status"] != "PENDING":
        raise HTTPException(400, f"Follow-up is already {instance['status']}")
    result = service.skip_follow_up(instance_id)
    return {"instance_id": instance_id, "status": result["status"]}


# ── Summary ────────────────────────────────────────────────────────────────


@router.get("/summary")
def follow_up_summary(
    service: FollowUpService = Depends(get_follow_up_service),
):
    """Get summary stats for the follow-up engine."""
    all_instances = service.list_follow_ups(limit=10000, offset=0)

    counts = {"PENDING": 0, "SENT": 0, "SKIPPED": 0, "FAILED": 0}
    for i in all_instances:
        s = i.get("status", "")
        if s in counts:
            counts[s] += 1

    return {
        "total": len(all_instances),
        "pending": counts["PENDING"],
        "sent": counts["SENT"],
        "skipped": counts["SKIPPED"],
        "failed": counts["FAILED"],
        "active_rules": len(service.list_rules()),
    }
