"""Quality gate — validate research brief meets minimum bar."""

from __future__ import annotations

from app.services.deep_research.schemas import ResearchBrief, StepResult, StepStatus


async def quality_gate(brief: ResearchBrief, min_sources: int = 2, min_confidence: float = 0.5) -> StepResult:
    """Check if research brief is sufficient for outreach."""
    result = StepResult(step_id="gate", step_type="quality_gate")

    passed = True
    failures = []

    if brief.total_sources < min_sources:
        passed = False
        failures.append(f"Sources: {brief.total_sources} < {min_sources}")

    if brief.confidence < min_confidence:
        passed = False
        failures.append(f"Confidence: {brief.confidence:.2f} < {min_confidence:.2f}")

    if not brief.lead_email:
        passed = False
        failures.append("No email found")

    result.raw_output = {
        "passed": passed,
        "sources": brief.total_sources,
        "confidence": brief.confidence,
        "email_found": bool(brief.lead_email),
        "failures": failures,
    }
    result.status = StepStatus.COMPLETED if passed else StepStatus.FAILED

    return result
