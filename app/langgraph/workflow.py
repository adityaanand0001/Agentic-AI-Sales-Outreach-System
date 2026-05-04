"""LangGraph workflow for autonomous mailing agent."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.services.email_generator import EmailGeneratorService
from app.services.gmail_oauth import GmailOAuthService
from app.services.ingestion import LeadIngestionService
from app.services.mail_tracker import MailTrackerService
from app.langgraph.enhanced_decision_node import IndustrialDecisionNode
from supabase import Client

logger = logging.getLogger(__name__)


# ── State Definition ──────────────────────────────────────────────────────────

class AgentState(TypedDict):
    """State for the mailing agent workflow."""

    # Input
    lead_id: Optional[str]
    batch_id: Optional[str]

    # Lead data
    lead_data: Optional[Dict[str, Any]]
    company_name: Optional[str]
    context: Optional[str]
    email: Optional[str]

    # Processing
    processing_stage: Literal[
        "DISCOVERED",
        "PRIORITIZED",
        "GENERATED",
        "QUALITY_CHECKED",
        "DECISION_MADE",
        "COMPLETED"
    ]
    priority_score: Optional[int]
    ai_confidence: Optional[float]
    requires_human: Optional[bool]

    # Email content
    email_subject: Optional[str]
    email_body: Optional[str]

    # Output
    tracker_id: Optional[str]
    gmail_message_id: Optional[str]
    action_taken: Optional[Literal["AUTO_SENT", "HUMAN_REVIEW", "SKIPPED", "FAILED"]]
    error: Optional[str]

    # Metadata
    start_time: Optional[str]
    end_time: Optional[str]
    processing_time: Optional[float]

    # Context for LLM decisions
    llm_context: Annotated[List[Any], add_messages]


# ── Node Definitions ──────────────────────────────────────────────────────────

class DiscoverLeadsNode:
    """Node to discover new leads from the database."""

    def __init__(self, ingestion_service: LeadIngestionService, db: Client):
        self.ingestion = ingestion_service
        self.db = db

    def __call__(self, state: AgentState) -> AgentState:
        """Discover and fetch lead data."""
        logger.info("Discovering leads for workflow")

        lead_id = state.get("lead_id")
        if not lead_id:
            # In a batch workflow, we'd fetch multiple leads
            # For now, we'll handle single lead processing
            return {**state, "error": "No lead_id provided"}

        try:
            # Fetch lead data
            lead = self.ingestion.fetch_lead_by_id(lead_id)
            if not lead:
                return {**state, "error": f"Lead {lead_id} not found"}

            return {
                **state,
                "lead_data": lead,
                "company_name": lead.get("name"),
                "context": lead.get("context"),
                "email": lead.get("email"),
                "processing_stage": "DISCOVERED",
                "start_time": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to discover lead {lead_id}: {e}")
            return {**state, "error": str(e), "processing_stage": "COMPLETED", "action_taken": "FAILED"}


class PrioritizeLeadNode:
    """Node to prioritize leads using AI."""

    def __init__(self, email_generator: EmailGeneratorService, db: Client):
        self.email_gen = email_generator
        self.db = db

    def __call__(self, state: AgentState) -> AgentState:
        """Calculate priority score for the lead."""
        logger.info("Prioritizing lead")

        lead_data = state.get("lead_data", {})
        if not lead_data:
            return {**state, "error": "No lead data available for prioritization"}

        try:
            # Calculate priority score (0-100)
            priority = self._calculate_priority(lead_data)

            # Create queue entry in database
            queue_entry = self._create_queue_entry(state, priority)
            self.db.table("processing_queue").insert(queue_entry).execute()

            return {
                **state,
                "priority_score": priority,
                "processing_stage": "PRIORITIZED",
            }
        except Exception as e:
            logger.error(f"Failed to prioritize lead: {e}")
            return {**state, "error": str(e)}

    def _calculate_priority(self, lead: Dict[str, Any]) -> int:
        """Calculate priority score for a lead (0-100) using AI."""
        company_name = lead.get("name", "Unknown")
        context = lead.get("context", "")
        
        # 1. AI Score (Primary weight: 70%)
        ai_score = self.email_gen.prioritize(company_name, context)
        final_score = ai_score * 70

        # 2. Heuristic signals (Secondary weight: 30%)
        heuristic = 0
        if company_name and len(company_name) > 2:
            heuristic += 10
        if "@" in lead.get("email", ""):
            heuristic += 10
        if len(context) > 100:
            heuristic += 10
            
        final_score += heuristic

        return min(100, max(1, int(final_score)))

    def _create_queue_entry(self, state: AgentState, priority: int) -> Dict[str, Any]:
        """Create processing queue entry."""
        now = datetime.now(timezone.utc).isoformat()
        return {
            "batch_id": state.get("batch_id", "single"),
            "lead_id": state.get("lead_id"),
            "priority": priority,
            "status": "PENDING",
            "processing_stage": "NEW",
            "scheduled_for": now,
            "metadata": {
                "company_name": state.get("company_name"),
                "email": state.get("email"),
                "context_preview": (state.get("context") or "")[:100],
            },
            "created_at": now,
            "updated_at": now,
        }




class GenerateEmailNode:
    """Node to generate personalized email using LLM."""

    def __init__(self, email_generator: EmailGeneratorService, db: Client):
        self.email_gen = email_generator
        self.db = db

    def __call__(self, state: AgentState) -> AgentState:
        """Generate personalized email for the lead."""
        logger.info("Generating email")

        company_name = state.get("company_name", "")
        context = state.get("context", "")
        recipient_email = state.get("email", "")

        if not recipient_email:
            return {**state, "error": "No email address for lead"}

        try:
            email_content = self.email_gen.generate(company_name, context, recipient_email)

            return {
                **state,
                "email_subject": email_content["subject"],
                "email_body": email_content["body_text"],
                "processing_stage": "GENERATED",
            }
        except Exception as e:
            logger.error(f"Failed to generate email: {e}")
            return {**state, "error": str(e)}


class QualityCheckNode:
    """Node to perform AI quality check on generated email."""

    def __init__(self, db: Client):
        self.db = db
        self.settings = get_settings()

    def __call__(self, state: AgentState) -> AgentState:
        """Check email quality using AI."""
        logger.info("Performing AI quality check")

        email_subject = state.get("email_subject", "")
        email_body = state.get("email_body", "")
        company_name = state.get("company_name", "")
        context = state.get("context", "")

        try:
            # Evaluate email quality
            confidence, requires_human = self._check_email_quality(
                email_subject, email_body, company_name, context, state.get("lead_data", {})
            )

            return {
                **state,
                "ai_confidence": confidence,
                "requires_human": requires_human,
                "processing_stage": "QUALITY_CHECKED",
            }
        except Exception as e:
            logger.error(f"Failed to perform quality check: {e}")
            return {**state, "error": str(e)}

    def _check_email_quality(self, subject: str, body: str, company_name: str, context: str = "", lead_data: dict = {}) -> tuple[float, bool]:
        """Check email quality with multi-signal scoring including context relevance."""
        score = 0.0
        max_score = 0.0

        # 1. Subject quality (max 0.15)
        max_score += 0.15
        if subject:
            if 5 < len(subject) < 80:
                score += 0.10
            if company_name and company_name.lower() in subject.lower():
                score += 0.05

        # 2. Body length (max 0.20)
        max_score += 0.20
        body_len = len(body)
        if 150 <= body_len <= 650:
            score += 0.20
        elif 80 <= body_len < 150 or 650 < body_len <= 1000:
            score += 0.12
        elif body_len > 1000:
            score += 0.05

        # 3. Company Personalization (max 0.20)
        max_score += 0.20
        if company_name and company_name.lower() in body.lower():
            score += 0.20

        # 4. Context Relevance (max 0.30) - IMPORTANT
        max_score += 0.30
        if context:
            ctx_lower = context.lower()
            body_lower = body.lower()
            # Extract keywords from context (words > 5 chars)
            keywords = [w.strip(".,!?:") for w in ctx_lower.split() if len(w) > 5]
            if keywords:
                matches = sum(1 for k in keywords if k in body_lower)
                relevance_ratio = matches / len(keywords)
                score += min(0.30, relevance_ratio * 0.5) # Strong boost for context matching

        # 5. Lead Name Personalization (max 0.10)
        max_score += 0.10
        contact_name = lead_data.get("contact_name") or lead_data.get("first_name")
        if contact_name and contact_name.lower() in body.lower():
            score += 0.10

        # 6. Professionalism signals (Greeting/Sign-off) (max 0.15)
        max_score += 0.15
        greetings = ["hi ", "hello ", "dear ", "hey "]
        sign_offs = ["best regards", "regards", "cheers", "best,", "sincerely", "thanks,", "thank you"]
        body_lower = body.lower()
        if any(body_lower.strip().startswith(g) for g in greetings):
            score += 0.07
        if any(s in body_lower for s in sign_offs):
            score += 0.08

        # 7. Call-to-Action (max 0.15)
        max_score += 0.15
        cta_phrases = ["let me know", "would you be open", "schedule a call", "happy to chat", "interested in", "quick call", "15 minutes", "connect"]
        if any(p in body_lower for p in cta_phrases):
            score += 0.15

        # 8. Spam/Quality Penalties (deduct up to -0.30)
        spam_words = ["buy now", "free money", "click here", "act now", "limited time", "winner", "congratulations", "guaranteed"]
        spam_hits = sum(1 for w in spam_words if w in body_lower)
        score -= min(0.30, spam_hits * 0.15)

        if body.count("!") > 3:
            score -= 0.10

        # Normalize
        confidence = max(0.0, min(1.0, score / max_score)) if max_score > 0 else 0.5
        requires_human = confidence < self.settings.auto_send_threshold

        return round(confidence, 3), requires_human


class DecisionNode:
    """Node to make final decision based on AI confidence."""

    def __init__(self, tracker: MailTrackerService, gmail: GmailOAuthService, db: Client):
        self.tracker = tracker
        self.gmail = gmail
        self.db = db
        self.settings = get_settings()

    def __call__(self, state: AgentState) -> AgentState:
        """Make final decision: auto-send, human review, or skip."""
        logger.info("Making final decision")

        confidence = state.get("ai_confidence", 0.0)
        requires_human = state.get("requires_human", True)

        try:
            # Create tracker record
            tracker_record = self.tracker.create_record(
                company_name=state.get("company_name", ""),
                email=state.get("email", ""),
                subject=state.get("email_subject", ""),
                body_preview=state.get("email_body", ""),
                context=state.get("context", ""),
                status="PENDING",
            )

            state["tracker_id"] = tracker_record["id"]
            auto_send_threshold = self.settings.auto_send_threshold

            # If SEND_EMAIL_DIRECTLY is false, always go to human review
            if not self.settings.send_email_directly:
                return self._human_review_decision(state, tracker_record["id"], confidence)

            if not requires_human and confidence >= auto_send_threshold:
                return self._auto_send_decision(state, tracker_record["id"])
            elif requires_human:
                return self._human_review_decision(state, tracker_record["id"], confidence)
            else:
                return self._skip_decision(state, tracker_record["id"])

        except Exception as e:
            logger.error(f"Failed to make decision: {e}")
            return {**state, "error": str(e), "action_taken": "FAILED"}

    def _auto_send_decision(self, state: AgentState, tracker_id: str) -> AgentState:
        """Handle auto-send decision."""
        try:
            # Send email
            msg_id = self.gmail.safe_send_email(
                recipient=state.get("email", ""),
                subject=state.get("email_subject", ""),
                body_text=state.get("email_body", ""),
            )

            # Update tracker
            self.tracker.update_status(
                tracker_id,
                "SENT",
                gmail_message_id=msg_id,
            )

            # Log AI decision
            self._log_ai_decision(
                tracker_id=tracker_id,
                decision_type="AUTO_APPROVAL",
                confidence=state.get("ai_confidence", 0.0),
            )

            return {
                **state,
                "gmail_message_id": msg_id,
                "action_taken": "AUTO_SENT",
                "processing_stage": "DECISION_MADE",
            }
        except Exception as e:
            logger.error(f"Auto-send failed: {e}")
            self.tracker.update_status(tracker_id, "FAILED", error=str(e))
            return {**state, "error": str(e), "action_taken": "FAILED"}

    def _human_review_decision(self, state: AgentState, tracker_id: str, confidence: float) -> AgentState:
        """Handle human review decision."""
        # Add to human review queue
        now = datetime.now(timezone.utc).isoformat()

        reason = "Low AI confidence"
        if confidence < 0.5:
            reason = "Very low confidence - needs human evaluation"
        elif confidence < 0.7:
            reason = "Moderate confidence - recommend review"

        review_entry = {
            "tracker_id": tracker_id,
            "reason": reason,
            "priority": int(100 - (confidence * 100)),  # Lower confidence = higher priority
            "status": "PENDING",
            "created_at": now,
            "updated_at": now,
        }

        self.db.table("human_review_queue").insert(review_entry).execute()

        # Log AI decision
        self._log_ai_decision(
            tracker_id=tracker_id,
            decision_type="HUMAN_REVIEW",
            confidence=confidence,
        )

        return {
            **state,
            "action_taken": "HUMAN_REVIEW",
            "processing_stage": "DECISION_MADE",
        }

    def _skip_decision(self, state: AgentState, tracker_id: str) -> AgentState:
        """Handle skip decision."""
        # Update tracker to rejected
        self.tracker.update_status(
            tracker_id,
            "REJECTED",
            error="Low AI confidence - skipped",
        )

        # Log AI decision
        self._log_ai_decision(
            tracker_id=tracker_id,
            decision_type="SKIP",
            confidence=state.get("ai_confidence", 0.0),
        )

        return {
            **state,
            "action_taken": "SKIPPED",
            "processing_stage": "DECISION_MADE",
        }

    def _log_ai_decision(self, tracker_id: str, decision_type: str, confidence: float) -> None:
        """Log AI decision to database."""
        now = datetime.now(timezone.utc).isoformat()

        decision_entry = {
            "tracker_id": tracker_id,
            "decision_type": decision_type,
            "confidence": confidence,
            "model_used": self.settings.llm_model,
            "created_at": now,
        }

        self.db.table("ai_decisions").insert(decision_entry).execute()


class CompletionNode:
    """Node to finalize processing and record metrics."""

    def __init__(self, db: Client):
        self.db = db

    def __call__(self, state: AgentState) -> AgentState:
        """Finalize processing and record metrics."""
        logger.info("Completing workflow")

        end_time = datetime.now(timezone.utc).isoformat()
        start_time = state.get("start_time")

        processing_time = 0.0
        if start_time:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            processing_time = (end_dt - start_dt).total_seconds()

        # Record metrics
        self._record_metrics(state, processing_time)

        return {
            **state,
            "end_time": end_time,
            "processing_time": processing_time,
            "processing_stage": "COMPLETED",
        }

    def _record_metrics(self, state: AgentState, processing_time: float) -> None:
        """Record processing metrics."""
        # This would update daily metrics table
        # Simplified for now
        pass

class ResearchNode:
    """Node to run deep research on a lead before email generation."""

    def __init__(self, email_gen: EmailGeneratorService, db: Client):
        self.email_gen = email_gen
        self.db = db

    async def __call__(self, state: AgentState) -> AgentState:
        """Run deep research pipeline and enrich state context."""
        logger.info("Running deep research for lead")
        from app.services.deep_research.engine import research_single_lead
        from app.services.deep_research.schemas import LeadInput

        company_name = state.get("company_name", "")

        if not company_name:
            return {**state, "processing_stage": "RESEARCHED"}

        try:
            lead = LeadInput(
                name=company_name,
                sector=state.get("context", "")[:80],
                size="",
            )

            brief = await research_single_lead(lead)

            research_context = ""
            if brief.profile:
                research_context += f"Company Profile: {brief.profile}\n"
            if brief.why_now:
                research_context += f"Why Now: {'; '.join(brief.why_now)}\n"
            if brief.pain_points:
                research_context += f"Pain Points: {'; '.join(brief.pain_points)}\n"
            if brief.hooks:
                research_context += f"Hooks: {'; '.join(h.hook for h in brief.hooks)}\n"

            existing_context = state.get("context") or ""
            return {
                **state,
                "processing_stage": "RESEARCHED",
                "context": existing_context + "\n\nRESEARCH BRIEF:\n" + research_context,
            }
        except Exception as e:
            logger.error(f"Deep research failed for {company_name}: {e}")
            return {**state, "processing_stage": "RESEARCHED"}


# ── Workflow Builder ──────────────────────────────────────────────────────────

def build_mailing_workflow(
    db: Client,
    ingestion: LeadIngestionService,
    email_gen: EmailGeneratorService,
    tracker: MailTrackerService,
    gmail: GmailOAuthService,
    enable_research: bool = True,
) -> StateGraph:
    """Build and return the LangGraph workflow."""

    # Create nodes
    discover_node = DiscoverLeadsNode(ingestion, db)
    prioritize_node = PrioritizeLeadNode(email_gen, db)
    generate_node = GenerateEmailNode(email_gen, db)
    quality_node = QualityCheckNode(db)
    decision_node = IndustrialDecisionNode(tracker, gmail, db)
    completion_node = CompletionNode(db)

    # Build workflow
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("discover", discover_node)
    workflow.add_node("prioritize", prioritize_node)

    if enable_research:
        research_node = ResearchNode(email_gen, db)
        workflow.add_node("research", research_node)

    workflow.add_node("generate", generate_node)
    workflow.add_node("quality_check", quality_node)
    workflow.add_node("decision", decision_node)
    workflow.add_node("complete", completion_node)

    # Define edges
    workflow.add_edge(START, "discover")
    workflow.add_edge("discover", "prioritize")

    if enable_research:
        workflow.add_edge("prioritize", "research")
        workflow.add_edge("research", "generate")
    else:
        workflow.add_edge("prioritize", "generate")

    workflow.add_edge("generate", "quality_check")
    workflow.add_edge("quality_check", "decision")
    workflow.add_edge("decision", "complete")
    workflow.add_edge("complete", END)

    return workflow