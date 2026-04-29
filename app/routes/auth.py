"""OAuth 2.0 authentication routes for Gmail."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.services.gmail_oauth import get_gmail_oauth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/google")
async def google_auth(request: Request):
    """Initiate Google OAuth 2.0 flow."""
    try:
        gmail_service = get_gmail_oauth_service()
        authorization_url = gmail_service.get_authorization_url()
        return RedirectResponse(authorization_url)
    except Exception as e:
        logger.error("Failed to generate auth URL: %s", e)
        raise HTTPException(500, "Failed to initiate authentication")


@router.get("/google/callback")
async def google_auth_callback(code: str, state: str = ""):
    """Handle Google OAuth 2.0 callback."""
    try:
        gmail_service = get_gmail_oauth_service()
        token_data = gmail_service.exchange_code_for_tokens(code)

        # Store tokens (in production, save to database with user ID)
        user_id = "default_user"  # In real app, get from session or JWT
        gmail_service.store_credentials(user_id, token_data)

        return {
            "message": "Authentication successful",
            "user_id": user_id,
            "has_credentials": True,
        }
    except Exception as e:
        logger.error("Failed to exchange code for tokens: %s", e)
        raise HTTPException(400, f"Failed to exchange code: {str(e)}")


@router.get("/status")
async def auth_status():
    """Check if user has valid Gmail credentials."""
    try:
        gmail_service = get_gmail_oauth_service()
        creds = gmail_service.get_credentials("default_user")
        return {
            "authenticated": creds is not None and creds.valid,
            "has_refresh_token": creds.refresh_token is not None if creds else False,
            "expired": creds.expired if creds else True,
        }
    except Exception as e:
        logger.error("Failed to check auth status: %s", e)
        return {"authenticated": False, "error": str(e)}


@router.post("/logout")
async def logout():
    """Clear stored credentials (in production, remove from database)."""
    try:
        # In production, remove from database
        # For now, just clear cache
        gmail_service = get_gmail_oauth_service()
        gmail_service._credentials_cache.clear()
        return {"message": "Logged out successfully"}
    except Exception as e:
        logger.error("Failed to logout: %s", e)
        raise HTTPException(500, "Failed to logout")
