"""LLM synthesize — merge all research into a concise research brief."""

from __future__ import annotations

import json
import logging

import google.generativeai as genai

from app.config.settings import get_settings
from app.services.deep_research.schemas import (
    ContactResult,
    IdentityResult,
    LeadInput,
    ResearchBrief,
    ResearchGap,
    ResearchHook,
    SignalItem,
    StepResult,
    StepStatus,
)

logger = logging.getLogger(__name__)


async def synthesize_brief(
    lead: LeadInput,
    contact: ContactResult | None = None,
    identity: IdentityResult | None = None,
    signals: list[SignalItem] | None = None,
    deep_dive_text: str = "",
) -> StepResult:
    """Use LLM to synthesize all research into a research brief."""
    result = StepResult(step_id="synthesize", step_type="llm_analyze")
    signals = signals or []

    import time
    start = time.time()

    # If we have nothing, return empty
    if not identity and not signals:
        result.status = StepStatus.SKIPPED
        result.error = "No research data to synthesize"
        return result

    settings = get_settings()
    try:
        genai.configure(api_key=settings.google_api_key)
        model = genai.GenerativeModel(settings.llm_model)

        prompt = _build_synthesis_prompt(lead, contact, identity, signals, deep_dive_text)

        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json", "temperature": 0.3},
        )

        parsed = json.loads(response.text or "{}")
        brief = _parse_brief(lead, contact, identity, signals, parsed)

        result.sources_used = list(set(s.source for s in signals)) if signals else []
        result.raw_output = brief.model_dump()
        result.status = StepStatus.COMPLETED

    except Exception as e:
        logger.error(f"LLM synthesize failed: {e}")
        # Fallback: build brief without LLM
        brief = _fallback_brief(lead, contact, identity, signals)
        result.raw_output = brief.model_dump()
        result.status = StepStatus.COMPLETED

    result.duration_ms = (time.time() - start) * 1000
    return result


def _build_synthesis_prompt(
    lead: LeadInput,
    contact: ContactResult | None,
    identity: IdentityResult | None,
    signals: list[SignalItem],
    deep_dive_text: str,
) -> str:
    """Build the LLM prompt for synthesis."""
    parts = [
        "You are a sales intelligence analyst. Synthesize the following research into a structured brief.\n",
        f"COMPANY: {lead.name}",
        f"INDUSTRY: {lead.sector}",
        f"SIZE: {lead.size}\n",
    ]

    if contact and (contact.person_name or contact.email):
        parts.append(
            f"CONTACT: {contact.person_name} - {contact.role} - {contact.email}"
        )

    if identity:
        id_fields = []
        if identity.location:
            id_fields.append(f"Location: {identity.location}")
        if identity.domain:
            id_fields.append(f"Domain: {identity.domain}")
        if identity.domain_age:
            id_fields.append(f"Domain age: {identity.domain_age}")
        if identity.email_provider:
            id_fields.append(f"Email: {identity.email_provider}")
        if identity.description:
            id_fields.append(f"Description: {identity.description[:300]}")
        if identity.rating:
            id_fields.append(f"Rating: {identity.rating} ({identity.review_count} reviews)")
        if identity.tech_stack:
            id_fields.append(f"Tech: {', '.join(identity.tech_stack)}")
        if id_fields:
            parts.append("IDENTITY:\n" + "\n".join(id_fields))

    if signals:
        parts.append("\nSIGNALS:")
        for s in signals:
            parts.append(f"[{s.signal_type}] {s.detail[:200]} (source: {s.source})")

    if deep_dive_text:
        parts.append(f"\nDEEP RESEARCH (browser):\n{deep_dive_text[:1500]}")

    parts.append("""
TASK: Output a JSON object:
{
  "profile": "3-sentence company description",
  "why_now": ["reason 1", "reason 2", "reason 3"],
  "pain_points": ["pain point 1", "pain point 2", "pain point 3"],
  "hooks": [{"hook": "outreach hook 1"}, {"hook": "outreach hook 2"}, {"hook": "outreach hook 3"}],
  "confidence": 0.75,
  "gaps": [{"gap": "what we don't know"}]
}

Rules:
- profile: concise but specific
- why_now: time-sensitive reasons to reach out THIS WEEK
- pain_points: problems relevant to Klyro's operational automation services
- hooks: personalized email opening lines referencing specific research findings
- confidence: 0-1 based on source quality and data freshness
- gaps: things we couldn't confirm
""")

    return "\n".join(parts)


def _parse_brief(
    lead: LeadInput,
    contact: ContactResult | None,
    identity: IdentityResult | None,
    signals: list[SignalItem],
    parsed: dict,
) -> ResearchBrief:
    """Parse LLM output into ResearchBrief."""
    return ResearchBrief(
        lead_name=lead.name,
        lead_email=contact.email if contact else "",
        person=contact or ContactResult(),
        identity=identity or IdentityResult(),
        signals=signals,
        profile=parsed.get("profile", ""),
        why_now=parsed.get("why_now", []),
        pain_points=parsed.get("pain_points", []),
        hooks=[ResearchHook(hook=h.get("hook", h) if isinstance(h, dict) else h) for h in parsed.get("hooks", [])],
        confidence=parsed.get("confidence", 0.5),
        total_sources=len(signals),
        gaps=[ResearchGap(gap=g.get("gap", g) if isinstance(g, dict) else g) for g in parsed.get("gaps", [])],
    )


def _fallback_brief(
    lead: LeadInput,
    contact: ContactResult | None,
    identity: IdentityResult | None,
    signals: list[SignalItem],
) -> ResearchBrief:
    """Build a brief without LLM when synthesizer fails."""
    hooks = []
    for s in signals[:3]:
        hooks.append(ResearchHook(hook=s.detail[:120]))
    if not hooks:
        hooks.append(ResearchHook(hook=f"Interested in how Klyro can help {lead.name} scale"))

    return ResearchBrief(
        lead_name=lead.name,
        lead_email=contact.email if contact else "",
        person=contact or ContactResult(),
        identity=identity or IdentityResult(),
        signals=signals,
        profile=identity.description if identity else "",
        why_now=["Relevant industry changes detected"] if signals else [],
        pain_points=[],
        hooks=hooks,
        confidence=min(0.7, len(signals) * 0.15),
        total_sources=len(signals),
        gaps=[ResearchGap(gap="LLM synthesis unavailable — brief built from raw signals")],
    )
