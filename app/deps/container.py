"""FastAPI dependency injection for services."""

from __future__ import annotations

from fastapi import Depends
from supabase import Client

from app.config.database import get_supabase
from app.services.ingestion import LeadIngestionService
from app.services.email_generator import EmailGeneratorService
from app.services.gmail_oauth import get_gmail_oauth_service
from app.services.mail_tracker import MailTrackerService
from app.services.autonomous_agent import AutonomousMailingAgent
from app.services.scheduler import AgentScheduler
from app.langgraph.agent import LangGraphAgentService


def get_lead_ingestion(db: Client = Depends(get_supabase)) -> LeadIngestionService:
    return LeadIngestionService(db)


def get_email_generator() -> EmailGeneratorService:
    return EmailGeneratorService()


def get_gmail_service():
    return get_gmail_oauth_service()


def get_mail_tracker(db: Client = Depends(get_supabase)) -> MailTrackerService:
    return MailTrackerService(db)


def get_autonomous_agent(
    db: Client = Depends(get_supabase),
    ingestion: LeadIngestionService = Depends(get_lead_ingestion),
    email_gen: EmailGeneratorService = Depends(get_email_generator),
    tracker: MailTrackerService = Depends(get_mail_tracker),
    gmail_service = Depends(get_gmail_service),
) -> AutonomousMailingAgent:
    return AutonomousMailingAgent(db, ingestion, email_gen, tracker, gmail_service)


def get_agent_scheduler(
    agent: AutonomousMailingAgent = Depends(get_autonomous_agent),
) -> AgentScheduler:
    return AgentScheduler(agent)


def get_langgraph_agent(
    db: Client = Depends(get_supabase),
    ingestion: LeadIngestionService = Depends(get_lead_ingestion),
    email_gen: EmailGeneratorService = Depends(get_email_generator),
    tracker: MailTrackerService = Depends(get_mail_tracker),
    gmail_service = Depends(get_gmail_service),
) -> LangGraphAgentService:
    return LangGraphAgentService(db, ingestion, email_gen, tracker, gmail_service)
