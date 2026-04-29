"""Pydantic schemas for the Mailing Agent API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


# ── Supabase source table (the table you configure with Name, Context, Email) ──

class CompanyLead(BaseModel):
    """Row from your configured Supabase table containing company data."""
    id: str = ""
    name: str = ""
    context: str = ""
    email: str = ""

    model_config = {"populate_by_name": True, "from_attributes": True}


# ── Mail Agent Tracker (the new table this agent maintains) ────────────────────

class MailAgentTracker(BaseModel):
    """Schema for the mail_agent_tracker table that keeps track of every email run."""
    id: str = ""
    company_name: str = ""
    email: str = ""
    mail_count: int = 0
    status: str = "PENDING"  # PENDING | APPROVED | SENT | REJECTED | FAILED
    email_subject: str = ""
    email_body_preview: str = ""
    gmail_message_id: str = ""
    error: str = ""
    created_at: str = ""
    updated_at: str = ""

    model_config = {"from_attributes": True}


# ── Email generation request / response ───────────────────────────────────────

class GenerateEmailRequest(BaseModel):
    lead_id: str


class GenerateEmailResponse(BaseModel):
    tracker_id: str
    company_name: str
    email: str
    subject: str
    body_text: str
    status: str = "PENDING"


class ApproveEmailRequest(BaseModel):
    tracker_id: str


class ApproveEmailResponse(BaseModel):
    tracker_id: str
    status: str
    gmail_message_id: str = ""


class UpdateDraftRequest(BaseModel):
    subject: str | None = None
    body_text: str | None = None


class RejectEmailRequest(BaseModel):
    tracker_id: str
    reason: str = ""


class RejectEmailResponse(BaseModel):
    tracker_id: str
    status: str


class RegenerateEmailRequest(BaseModel):
    tracker_id: str
    feedback: str


class BulkApproveRequest(BaseModel):
    tracker_ids: list[str]


# ── List / Dashboard ──────────────────────────────────────────────────────────

class TrackerRecord(BaseModel):
    id: str | None = ""
    company_name: str | None = ""
    email: str | None = ""
    mail_count: int | None = 0
    status: str | None = "PENDING"
    email_subject: str | None = ""
    email_body_preview: str | None = ""
    created_at: str | None = ""
    updated_at: str | None = ""


class DashboardSummary(BaseModel):
    total: int
    pending: int
    approved: int
    sent: int
    rejected: int
    failed: int


# ── Leads (from the configured source table) ──────────────────────────────────

class LeadRecord(BaseModel):
    id: str | None = ""
    name: str | None = ""
    context: str | None = ""
    email: str | None = ""
    is_new: bool | None = True

    model_config = {"from_attributes": True}


# ── Autonomous Agent ─────────────────────────────────────────────────────────

class AgentStatusResponse(BaseModel):
    agent_status: str
    queue_status: dict
    pending_human_reviews: int
    auto_send_threshold: float
    batch_size: int


class BatchRunResponse(BaseModel):
    batch_id: str
    status: str
    summary: dict = {}
    error: str = ""
    message: str = ""


class AgentConfigUpdate(BaseModel):
    auto_send_threshold: float = 0.8
    batch_size: int = 50
    processing_delay: float = 2.0
    message: str = ""


class SchedulerStatusResponse(BaseModel):
    is_running: bool
    run_interval_minutes: int
    max_concurrent_batches: int
    active_batches: list[str]
    active_batch_count: int
    total_runs: int
    recent_runs: list[dict]


class SchedulerConfigUpdate(BaseModel):
    run_interval_minutes: int = 60
    max_concurrent_batches: int = 1


class LogEntryResponse(BaseModel):
    id: str
    queue_id: str | None = None
    tracker_id: str | None = None
    decision_type: str
    input_data: dict | None = None
    output_data: dict | None = None
    confidence: float | None = None
    model_used: str | None = None
    created_at: str


class BatchSummaryResponse(BaseModel):
    batch_id: str
    total_leads: int
    completed: int
    failed: int
    auto_sent: int
    human_review: int
    avg_confidence: float
    created_at: str


# ── Templates ──────────────────────────────────────────────────────────────

class TemplateCreate(BaseModel):
    name: str
    subject: str = ""
    body: str = ""


class TemplateUpdate(BaseModel):
    name: str | None = None
    subject: str | None = None
    body: str | None = None


class TemplateResponse(BaseModel):
    id: str
    name: str
    subject: str = ""
    body: str = ""
    created_at: str = ""
    updated_at: str = ""


# ── Bulk Reject ─────────────────────────────────────────────────────────────

class BulkRejectRequest(BaseModel):
    tracker_ids: list[str]
    reason: str = ""


# ── Compliance ─────────────────────────────────────────────────────────────

class ComplianceEvent(BaseModel):
    id: str
    email: str = ""
    name: str = ""
    event_type: str = ""  # unsubscribe | bounce | spam | gdpr
    created_at: str = ""
    source: str = ""


class ComplianceSummary(BaseModel):
    total: int
    unsubscribes: int
    bounces: int
    spam: int
    gdpr: int  # Renamed to avoid conflict


# ── Warmup ─────────────────────────────────────────────────────────────────

class WarmupDay(BaseModel):
    label: str = ""
    sent: int = 0
    bounced: int = 0
    bounce_rate: float = 0.0


class WarmupResponse(BaseModel):
    today: WarmupDay = {}
    history: list[WarmupDay] = []
    reputation: str = "healthy"
    recommended_daily: int = 80
