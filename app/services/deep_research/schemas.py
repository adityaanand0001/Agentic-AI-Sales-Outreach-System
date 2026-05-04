"""Schemas for the deep research pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Lead input ─────────────────────────────────────────────────────────────────

class LeadInput(BaseModel):
    name: str
    sector: str = ""
    size: str = ""
    email: str = ""  # may be empty, filled by contact discovery


# ── Step types ─────────────────────────────────────────────────────────────────

class StepType(str, Enum):
    CONTACT_DISCOVERY = "contact_discovery"
    IDENTITY_RESEARCH = "identity_research"
    SIGNAL_DISCOVERY = "signal_discovery"
    BROWSER_EXPLORE = "browser_explore"
    LLM_ANALYZE = "llm_analyze"
    QUALITY_GATE = "quality_gate"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class StepResult(BaseModel):
    step_id: str
    step_type: StepType
    status: StepStatus = StepStatus.PENDING
    started_at: str = ""
    completed_at: str = ""
    duration_ms: float = 0
    sources_used: list[str] = Field(default_factory=list)
    raw_output: dict[str, Any] = Field(default_factory=dict)
    error: str = ""


# ── Contact discovery outputs ──────────────────────────────────────────────────

class ContactResult(BaseModel):
    person_name: str = ""
    role: str = ""
    email: str = ""
    email_confidence: float = 0.0
    linkedin_url: str = ""
    alternative_emails: list[str] = Field(default_factory=list)
    phone: str = ""
    sources: list[str] = Field(default_factory=list)


# ── Identity research outputs ──────────────────────────────────────────────────

class IdentityResult(BaseModel):
    company_name: str = ""
    industry: str = ""  # from CSV sector
    size: str = ""      # from CSV
    location: str = ""
    founded: str = ""
    domain: str = ""
    domain_age: str = ""
    email_provider: str = ""
    tech_stack: list[str] = Field(default_factory=list)
    description: str = ""
    social_profiles: dict[str, str] = Field(default_factory=dict)
    rating: str = ""
    review_count: int = 0
    crunchbase_url: str = ""
    funding_summary: str = ""


# ── Signal / discovery outputs ─────────────────────────────────────────────────

class SignalItem(BaseModel):
    signal_type: str  # "award", "pain", "demand", "growth", "launch", "competitor", "regulation", "industry"
    source: str
    source_url: str = ""
    detail: str
    relevance: str = ""  # why it matters for outreach


# ── Browser exploration actions ────────────────────────────────────────────────

class BrowserAction(BaseModel):
    action: str  # navigate, scroll_down, click, type, extract, paginate, wait
    url: str = ""
    selector: str = ""
    text: str = ""
    count: int = 1
    limit: int = 5
    max_pages: int = 1
    next_selector: str = ""


class BrowserSequence(BaseModel):
    site_url: str
    actions: list[BrowserAction]


# ── Research brief (final output) ──────────────────────────────────────────────

class ResearchHook(BaseModel):
    hook: str  # email-ready personalized hook


class ResearchGap(BaseModel):
    gap: str  # what we don't know


class ResearchBrief(BaseModel):
    lead_name: str
    lead_email: str = ""

    # Contact
    person: ContactResult = Field(default_factory=ContactResult)

    # Identity
    identity: IdentityResult = Field(default_factory=IdentityResult)

    # Signals
    signals: list[SignalItem] = Field(default_factory=list)

    # Analysis
    profile: str = ""  # 3-sentence company description
    why_now: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    hooks: list[ResearchHook] = Field(default_factory=list)

    # Meta
    confidence: float = 0.0
    total_sources: int = 0
    gaps: list[ResearchGap] = Field(default_factory=list)
    research_date: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── Pipeline configuration ─────────────────────────────────────────────────────

class StepConfig(BaseModel):
    step_id: str
    step_type: StepType
    depends_on: list[str] = Field(default_factory=list)
    required: bool = True
    timeout_seconds: int = 60
    config: dict[str, Any] = Field(default_factory=dict)


class SourceConfig(BaseModel):
    apollo_enrichment: bool = False
    linkedin_search: bool = True
    whois_lookup: bool = True
    google_maps: bool = True
    builtwith: bool = False
    yelp: bool = True
    google_news: bool = True
    google_web: bool = True
    social_scan: bool = True
    crunchbase: bool = False
    g2_reviews: bool = False
    browser_deep_dive: bool = False


class PipelineConfig(BaseModel):
    name: str
    steps: list[StepConfig]
    sources: SourceConfig = Field(default_factory=SourceConfig)
    quality_gate_min_sources: int = 2
    quality_gate_min_confidence: float = 0.5
    concurrency: int = 10


# ── Batch progress ─────────────────────────────────────────────────────────────

class BatchProgress(BaseModel):
    batch_id: str
    pipeline_name: str
    total_leads: int
    processed: int = 0
    contacts_found: int = 0
    briefs_generated: int = 0
    errors: int = 0
    skipped: int = 0
    status: str = "RUNNING"  # RUNNING, PAUSED, COMPLETED, STOPPED
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    phase: str = "contact_discovery"  # current phase
    lead_results: list[dict] = Field(default_factory=list)  # last 20 results for live feed
