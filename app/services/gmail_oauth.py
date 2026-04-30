"""Gmail OAuth 2.0 for web applications."""

from __future__ import annotations

import base64
import json
import logging
import os
import pickle
import time
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import Any, Dict, Optional, Tuple

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

# OAuth 2.0 scopes for Gmail
SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]


class GmailOAuthService:
    """
    Gmail OAuth 2.0 service for web applications.

    Flow:
    1. User visits /api/auth/google → redirects to Google OAuth consent screen
    2. Google redirects back to /api/auth/google/callback with code
    3. Exchange code for tokens, store in database (or session)
    4. Use tokens to send emails
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._credentials_cache: dict[str, Credentials] = {}

    # ── OAuth Flow ──────────────────────────────────────────────────────────────

    def get_authorization_url(self, state: str = "") -> str:
        """Generate Google OAuth 2.0 authorization URL manually to avoid PKCE issues."""
        from urllib.parse import urlencode
        
        params = {
            "client_id": self.settings.google_client_id,
            "redirect_uri": self.settings.google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "include_granted_scopes": "true",
        }
        base_url = "https://accounts.google.com/o/oauth2/v2/auth"
        return f"{base_url}?{urlencode(params)}"

    def exchange_code_for_tokens(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for access/refresh tokens using a direct POST request."""
        import httpx
        from datetime import datetime, timedelta

        data = {
            "code": code,
            "client_id": self.settings.google_client_id,
            "client_secret": self.settings.google_client_secret,
            "redirect_uri": self.settings.google_redirect_uri,
            "grant_type": "authorization_code",
        }

        response = httpx.post("https://oauth2.googleapis.com/token", data=data)
        if response.status_code != 200:
            raise Exception(f"Failed to exchange code: {response.text}")

        tokens = response.json()
        
        # Calculate expiry
        expiry = None
        if "expires_in" in tokens:
            expiry = (datetime.now() + timedelta(seconds=tokens["expires_in"])).isoformat()

        token_data = {
            "token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": self.settings.google_client_id,
            "client_secret": self.settings.google_client_secret,
            "scopes": tokens.get("scope", "").split(" "),
            "expiry": expiry,
        }

        # Cache for this session
        user_id = "default_user"
        self.store_credentials(user_id, token_data)

        return token_data

    def _create_flow(self) -> Flow:
        """Create OAuth 2.0 flow with client secrets."""
        client_secrets = {
            "web": {
                "client_id": self.settings.google_client_id,
                "client_secret": self.settings.google_client_secret,
                "redirect_uris": [self.settings.google_redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

        return Flow.from_client_config(
            client_secrets,
            scopes=SCOPES,
            redirect_uri=self.settings.google_redirect_uri,
        )

    # ── Credential Management ───────────────────────────────────────────────────

    def get_credentials(self, user_id: str = "default_user") -> Credentials | None:
        """Get credentials for a user (from cache or storage)."""
        # Check cache first
        if user_id in self._credentials_cache:
            creds = self._credentials_cache[user_id]
            if creds and creds.valid:
                return creds
            elif creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    return creds
                except Exception as e:
                    logger.error("Failed to refresh token: %s", e)
                    return None

        # In production, load from database
        # For now, return None if not in cache
        return None

    def store_credentials(self, user_id: str, token_data: dict) -> None:
        """Store credentials (in production, save to database)."""
        creds = Credentials(
            token=token_data["token"],
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data["token_uri"],
            client_id=token_data["client_id"],
            client_secret=token_data["client_secret"],
            scopes=token_data["scopes"],
        )
        if token_data.get("expiry"):
            creds.expiry = datetime.fromisoformat(token_data["expiry"])

        self._credentials_cache[user_id] = creds

    # ── Gmail Operations ────────────────────────────────────────────────────────

    def get_gmail_service(self, user_id: str = "default_user"):
        """Get authenticated Gmail service instance."""
        creds = self.get_credentials(user_id)
        if not creds:
            raise ValueError(f"No valid credentials for user {user_id}")

        if not self.settings.verify_ssl:
            import httplib2
            import google_auth_httplib2
            
            # Create an insecure http client for Google API
            http = httplib2.Http(disable_ssl_certificate_validation=True)
            return build("gmail", "v1", http=google_auth_httplib2.AuthorizedHttp(creds, http=http))
            
        return build("gmail", "v1", credentials=creds)

    def send_email(
        self,
        recipient: str,
        subject: str,
        body_text: str,
        body_html: str = "",
        user_id: str = "default_user",
        thread_id: str | None = None,
    ) -> tuple[str, str | None]:
        """Send email via Gmail API.

        Returns (gmail_message_id, thread_id).
        If thread_id is provided, the reply is appended to the existing thread.
        """
        service = self.get_gmail_service(user_id)
        msg = self._build_mime(recipient, subject, body_text, body_html)
        raw = self._encode(msg)

        body = {"raw": raw}
        if thread_id:
            body["threadId"] = thread_id

        resp = (
            service.users()
            .messages()
            .send(userId="me", body=body)
            .execute()
        )
        return resp.get("id", ""), resp.get("threadId")

    def create_draft(
        self,
        recipient: str,
        subject: str,
        body_text: str,
        body_html: str = "",
        user_id: str = "default_user",
    ) -> str:
        """Create a Gmail draft."""
        service = self.get_gmail_service(user_id)
        msg = self._build_mime(recipient, subject, body_text, body_html)
        raw = self._encode(msg)

        resp = (
            service.users()
            .drafts()
            .create(userId="me", body={"message": {"raw": raw}})
            .execute()
        )
        return resp.get("id", "")

    # ── Retry Wrapper ───────────────────────────────────────────────────────────

    def _with_retries(self, fn, **kwargs) -> tuple[str, str | None]:
        last_error = ""
        for attempt in range(1, self.settings.gmail_max_retries + 1):
            try:
                return fn(**kwargs)
            except HttpError as exc:
                last_error = str(exc)
                if exc.resp.status in (429, 500, 503) and attempt < self.settings.gmail_max_retries:
                    logger.warning("Gmail HTTP %s – retry %d/%d", exc.resp.status, attempt, self.settings.gmail_max_retries)
                    time.sleep(self.settings.gmail_retry_delay_sec * attempt)
                else:
                    raise
            except Exception as exc:
                last_error = str(exc)
                logger.error("Gmail unexpected error: %s", exc)
                raise
        raise RuntimeError(f"Gmail operation failed after retries: {last_error}")

    def safe_send_email(self, recipient: str, subject: str, body_text: str, body_html: str = "", user_id: str = "default_user", thread_id: str | None = None) -> tuple[str, str | None]:
        return self._with_retries(
            self.send_email,
            recipient=recipient,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            user_id=user_id,
            thread_id=thread_id,
        )

    def safe_create_draft(self, recipient: str, subject: str, body_text: str, body_html: str = "", user_id: str = "default_user") -> str:
        return self._with_retries(
            self.create_draft,
            recipient=recipient,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            user_id=user_id,
        )

    def check_daily_quota(self, db: Any, limit: int = 450) -> bool:
        """Check if we are within the safe daily sending quota."""
        # Calculate 24 hours ago
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        
        # Count SENT records in the last 24h
        resp = db.table("mail_agent_tracker") \
            .select("id", count="exact") \
            .eq("status", "SENT") \
            .gt("created_at", yesterday) \
            .execute()
        
        sent_count = resp.count or 0
        logger.info(f"Daily Quota Check: {sent_count}/{limit} emails sent in last 24h")
        return sent_count < limit

    def enhanced_send_email(
        self,
        recipient: str,
        subject: str,
        body_text: str,
        body_html: str = "",
        user_id: str = "default_user"
    ) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
        """Send email with enhanced error handling and recovery.

        Returns:
            Tuple of (message_id, error_code, error_details)
            - message_id: Gmail message ID if successful
            - error_code: Error code if failed (see GmailErrorHandler)
            - error_details: Additional error information
        """
        from app.services.gmail_error_handler import EnhancedGmailService, GmailErrorHandler

        # Create error handler with settings
        error_handler = GmailErrorHandler(
            max_retries=self.settings.gmail_max_retries,
            base_delay=self.settings.gmail_retry_delay_sec
        )

        # Create enhanced service
        enhanced_service = EnhancedGmailService(self, error_handler)

        # Send with enhanced error handling
        return enhanced_service.send_email_with_recovery(
            recipient=recipient,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            user_id=user_id
        )

    # ── Reply Detection ──────────────────────────────────────────────────────────

    def check_for_replies(self, user_id: str = "default_user") -> list[dict]:
        """Scan Gmail inbox for potential replies to emails we sent.

        Returns list of dicts with:
            thread_id, gmail_message_id, sender_email, subject, matched_tracker_id, company_name, recipient_email
        """
        service = self.get_gmail_service(user_id)
        potential_replies = []

        try:
            resp = (
                service.users()
                .messages()
                .list(userId="me", q="in:inbox", maxResults=50)
                .execute()
            )
        except Exception as e:
            logger.error("Failed to list inbox messages: %s", e)
            return []

        messages = resp.get("messages", [])
        if not messages:
            return []

        for m in messages:
            try:
                full = (
                    service.users()
                    .messages()
                    .get(
                        userId="me", id=m["id"],
                        format="metadata",
                        metadataHeaders=["From", "Subject", "In-Reply-To", "References", "Message-ID"]
                    )
                    .execute()
                )
                headers = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
                # Skip if no In-Reply-To — it's not a reply
                if not headers.get("In-Reply-To") and not headers.get("References"):
                    continue
                potential_replies.append({
                    "gmail_message_id": m["id"],
                    "thread_id": full.get("threadId"),
                    "sender_email": headers.get("From", ""),
                    "subject": headers.get("Subject", ""),
                    "message_id_header": headers.get("Message-ID", ""),
                    "in_reply_to": headers.get("In-Reply-To", ""),
                })
            except Exception as e:
                logger.warning("Failed to fetch message %s: %s", m["id"], e)

        return potential_replies

    # ── MIME Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _build_mime(
        recipient: str,
        subject: str,
        body_text: str,
        body_html: str,
    ) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["to"] = recipient
        msg["subject"] = subject
        msg["from"] = "me"  # Gmail will use the authenticated user's email
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))
        return msg

    @staticmethod
    def _encode(msg: MIMEMultipart) -> str:
        return base64.urlsafe_b64encode(msg.as_bytes()).decode()


# Singleton instance
_gmail_oauth_service = GmailOAuthService()


def get_gmail_oauth_service() -> GmailOAuthService:
    return _gmail_oauth_service
