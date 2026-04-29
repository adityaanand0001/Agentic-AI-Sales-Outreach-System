"""Application configuration via environment variables."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Supabase ────────────────────────────────────────────────────────────────
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_anon_key: str = ""

    # ── Tables ──────────────────────────────────────────────────────────────────
    supabase_leads_table: str = "leads"
    supabase_events_table: str = "campaign_events"
    supabase_mail_agent_table: str = "mail_agent_tracker"

    # ── Google OAuth 2.0 Configuration ──────────────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"

    # ── Sender ──────────────────────────────────────────────────────────────────
    sender_name: str = "Klyro Team"

    # ── Email defaults ──────────────────────────────────────────────────────────
    send_email_directly: bool = False

    # ── Ingestion ───────────────────────────────────────────────────────────────
    ingest_batch_size: int = 50
    ingest_min_score: float = 0.0

    # ── Retry ───────────────────────────────────────────────────────────────────
    gmail_max_retries: int = 3
    gmail_retry_delay_sec: float = 2.0

    # ── LLM ─────────────────────────────────────────────────────────────────────
    openai_api_key: str = ""
    google_api_key: str = ""
    llm_provider: str = "gemini"  # "openai" or "gemini"
    llm_model: str = "gemini-1.5-flash"

    # ── LangGraph ───────────────────────────────────────────────────────────────
    langgraph_workflow_version: str = "1.0.0"
    auto_send_threshold: float = 0.8
    batch_size: int = 50
    processing_delay: float = 2.0
    max_retries: int = 3

    # ── Security ────────────────────────────────────────────────────────────────
    verify_ssl: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
