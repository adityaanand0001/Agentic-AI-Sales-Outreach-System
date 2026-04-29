"""Supabase client singleton."""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from app.config.settings import get_settings


@lru_cache
def get_supabase() -> Client:
    settings = get_settings()
    print(f"DEBUG: get_supabase() called. verify_ssl={settings.verify_ssl}")
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
