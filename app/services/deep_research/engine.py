"""Deep Research Pipeline Engine — orchestrate multi-step research per lead."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from app.services.deep_research.cache import get_cached_brief, set_cached_brief
from app.services.deep_research.schemas import (
    BatchProgress,
    ContactResult,
    IdentityResult,
    LeadInput,
    PipelineConfig,
    ResearchBrief,
    SignalItem,
    SourceConfig,
    StepResult,
    StepStatus,
)
from app.services.deep_research.steps.browser import deep_explore
from app.services.deep_research.steps.contact import discover_contact
from app.services.deep_research.steps.discovery import discover_signals
from app.services.deep_research.steps.identity import research_identity
from app.services.deep_research.steps.quality_gate import quality_gate
from app.services.deep_research.steps.synthesize import synthesize_brief

logger = logging.getLogger(__name__)

DEFAULT_PIPELINE = PipelineConfig(
    name="standard_b2b",
    steps=[
        {"step_id": "find_person", "step_type": "contact_discovery", "depends_on": [], "required": True},
        {"step_id": "identify", "step_type": "identity_research", "depends_on": ["find_person"]},
        {"step_id": "discover", "step_type": "signal_discovery", "depends_on": ["identify"]},
        {"step_id": "synthesize", "step_type": "llm_analyze", "depends_on": ["identify", "discover"]},
        {"step_id": "gate", "step_type": "quality_gate", "depends_on": ["synthesize"]},
    ],
    concurrency=10,
)


async def research_single_lead(
    lead: LeadInput,
    pipeline: PipelineConfig | None = None,
    db=None,
    lead_id: str = "",
) -> ResearchBrief:
    """Research one lead through the full pipeline. Optionally persist to Supabase."""
    pipeline = pipeline or DEFAULT_PIPELINE

    # Check cache first
    cached = get_cached_brief(lead.name)
    if cached:
        logger.info(f"Cache hit for {lead.name}")
        return cached

    # Step outputs
    contact = ContactResult()
    identity = IdentityResult()
    signals: list[SignalItem] = []
    deep_dive_text = ""

    # Run steps in dependency order
    for step_config in pipeline.steps:
        step_type = step_config.step_type if hasattr(step_config, "step_type") else step_config["step_type"]
        step_id = step_config.step_id if hasattr(step_config, "step_id") else step_config["step_id"]
        config = step_config.config if hasattr(step_config, "config") else step_config.get("config", {})

        if step_type == "contact_discovery":
            step_result = await discover_contact(lead, config)
            if step_result.status == StepStatus.COMPLETED:
                contact = ContactResult(**step_result.raw_output)
                lead.email = contact.email

        elif step_type == "identity_research":
            step_result = await research_identity(lead, pipeline.sources)
            if step_result.status == StepStatus.COMPLETED:
                identity = IdentityResult(**step_result.raw_output)

        elif step_type == "signal_discovery":
            step_result = await discover_signals(lead, identity, pipeline.sources)
            if step_result.status == StepStatus.COMPLETED:
                raw_signals = step_result.raw_output.get("signals", [])
                signals = [SignalItem(**s) for s in raw_signals]

        elif step_type == "browser_explore":
            step_result = await deep_explore(lead, identity, pipeline.sources)
            if step_result.status == StepStatus.COMPLETED:
                deep_dive_text = str(step_result.raw_output.get("pages", []))

        elif step_type == "llm_analyze":
            step_result = await synthesize_brief(lead, contact, identity, signals, deep_dive_text)
            if step_result.status == StepStatus.COMPLETED:
                brief = ResearchBrief(**step_result.raw_output)
            else:
                brief = ResearchBrief(lead_name=lead.name, lead_email=lead.email, confidence=0.0)

        elif step_type == "quality_gate":
            gate = await quality_gate(brief, pipeline.quality_gate_min_sources, pipeline.quality_gate_min_confidence)
            brief.confidence = brief.confidence if gate.status == StepStatus.COMPLETED else brief.confidence

    # Cache result
    set_cached_brief(brief)

    # Persist to Supabase if available
    if db and brief.lead_email:
        _persist_brief_to_db(db, brief, lead_id)

    return brief


def _persist_brief_to_db(db, brief: ResearchBrief, lead_id: str = "") -> str:
    """Store research brief in Supabase, returns the brief UUID."""
    now = datetime.now(timezone.utc).isoformat()

    brief_data = {
        "lead_name": brief.lead_name,
        "lead_email": brief.lead_email,
        "person_name": brief.person.person_name,
        "person_role": brief.person.role,
        "person_linkedin": brief.person.linkedin_url,
        "person_email": brief.person.email,
        "person_email_confidence": brief.person.email_confidence,
        "person_sources": brief.person.sources,
        "company_domain": brief.identity.domain,
        "company_location": brief.identity.location,
        "company_description": brief.identity.description,
        "company_tech_stack": brief.identity.tech_stack,
        "company_social": brief.identity.social_profiles,
        "company_rating": brief.identity.rating,
        "company_reviews": brief.identity.review_count,
        "signals": [s.model_dump() for s in brief.signals],
        "profile": brief.profile,
        "why_now": brief.why_now,
        "pain_points": brief.pain_points,
        "hooks": [h.hook for h in brief.hooks],
        "confidence": brief.confidence,
        "total_sources": brief.total_sources,
        "gaps": [g.gap for g in brief.gaps],
        "sources_used": [],
        "raw_data": brief.model_dump(),
        "created_at": now,
        "updated_at": now,
    }

    if lead_id:
        brief_data["lead_id"] = lead_id

    try:
        resp = db.table("research_briefs").insert(brief_data).execute()
        if resp.data:
            brief_id = resp.data[0].get("id", "")
            return brief_id
    except Exception as e:
        logger.warning(f"Failed to persist research brief to Supabase: {e}")

    return ""


async def research_batch(
    leads: list[LeadInput],
    pipeline: PipelineConfig | None = None,
    db=None,
    lead_map: dict[str, str] | None = None,
) -> BatchProgress:
    """Research a batch of leads with concurrency. Optionally persist to Supabase."""
    pipeline = pipeline or DEFAULT_PIPELINE
    batch_id = f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    lead_map = lead_map or {}

    progress = BatchProgress(
        batch_id=batch_id,
        pipeline_name=pipeline.name,
        total_leads=len(leads),
    )

    queue = asyncio.Queue(maxsize=len(leads) * 2)
    for i, lead in enumerate(leads):
        await queue.put((i, lead))

    briefs: list[ResearchBrief | None] = [None] * len(leads)

    async def worker():
        while True:
            try:
                idx, lead = await queue.get()
            except asyncio.QueueEmpty:
                return
            try:
                lid = lead_map.get(lead.name, "")
                brief = await research_single_lead(lead, pipeline, db=db, lead_id=lid)
                briefs[idx] = brief
                progress.processed += 1
                if brief.lead_email:
                    progress.contacts_found += 1
                if brief.confidence > 0:
                    progress.briefs_generated += 1
                progress.lead_results.append({
                    "name": lead.name,
                    "email": brief.lead_email,
                    "confidence": brief.confidence,
                    "status": "completed",
                })
            except Exception as e:
                logger.error(f"Failed to research {lead.name}: {e}")
                progress.processed += 1
                progress.errors += 1
                progress.lead_results.append({
                    "name": lead.name,
                    "status": "failed",
                    "error": str(e)[:100],
                })
            finally:
                queue.task_done()
                progress.lead_results = progress.lead_results[-20:]  # keep last 20

    workers = [asyncio.create_task(worker()) for _ in range(pipeline.concurrency)]
    await queue.join()

    for w in workers:
        w.cancel()

    progress.status = "COMPLETED"
    return progress


def leads_from_csv(path: str) -> list[LeadInput]:
    """Parse CSV file into list of LeadInput."""
    import csv

    leads = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            leads.append(LeadInput(
                name=(row.get("name") or row.get("Name") or row.get("company") or row.get("Company") or "").strip(),
                sector=(row.get("sector") or row.get("Sector") or row.get("industry") or row.get("Industry") or "").strip(),
                size=(row.get("size") or row.get("Size") or row.get("employees") or row.get("Employees") or "").strip(),
            ))
    return [l for l in leads if l.name]
