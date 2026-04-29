"""Enhanced Gmail API error handling and recovery."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class GmailErrorType(Enum):
    """Categories of Gmail API errors."""

    # Authentication & Authorization
    AUTH_TOKEN_EXPIRED = "auth_token_expired"
    AUTH_TOKEN_REVOKED = "auth_token_revoked"
    AUTH_INSUFFICIENT_SCOPES = "auth_insufficient_scopes"
    AUTH_USER_DISABLED = "auth_user_disabled"

    # Rate Limiting & Quotas
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    DAILY_QUOTA_EXCEEDED = "daily_quota_exceeded"
    USER_QUOTA_EXCEEDED = "user_quota_exceeded"

    # Recipient Errors
    RECIPIENT_NOT_FOUND = "recipient_not_found"
    RECIPIENT_MAILBOX_FULL = "recipient_mailbox_full"
    RECIPIENT_DOMAIN_NOT_FOUND = "recipient_domain_not_found"
    RECIPIENT_REJECTED = "recipient_rejected"

    # Content Errors
    MESSAGE_TOO_LARGE = "message_too_large"
    SPAM_DETECTED = "spam_detected"
    MALFORMED_MESSAGE = "malformed_message"

    # Network & Server Errors
    NETWORK_TIMEOUT = "network_timeout"
    SERVICE_UNAVAILABLE = "service_unavailable"
    INTERNAL_SERVER_ERROR = "internal_server_error"

    # Unknown/Other
    UNKNOWN_ERROR = "unknown_error"
    VALIDATION_ERROR = "validation_error"


class RecoveryAction(Enum):
    """Possible recovery actions for different error types."""

    RETRY_IMMEDIATE = "retry_immediate"          # Retry immediately (transient error)
    RETRY_WITH_BACKOFF = "retry_with_backoff"    # Retry with exponential backoff
    REFRESH_TOKEN = "refresh_token"              # Refresh OAuth token and retry
    QUEUE_FOR_LATER = "queue_for_later"          # Queue email for later sending
    SKIP_PERMANENTLY = "skip_permanently"        # Skip this email permanently
    PAUSE_SENDING = "pause_sending"              # Pause all sending temporarily
    REQUIRE_HUMAN_INTERVENTION = "require_human_intervention"  # Needs manual fix
    UPDATE_CONFIGURATION = "update_configuration" # Update system configuration


class GmailErrorHandler:
    """Handles Gmail API errors with intelligent recovery strategies."""

    def __init__(self, max_retries: int = 3, base_delay: float = 2.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.error_stats: Dict[str, int] = {}
        self.circuit_breaker_state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.circuit_breaker_failures = 0
        self.circuit_breaker_threshold = 5
        self.circuit_breaker_reset_timeout = 60  # seconds

    def classify_error(self, error: Exception) -> Tuple[GmailErrorType, Dict[str, Any]]:
        """Classify Gmail API error and extract relevant information."""

        error_details = {
            "error_message": str(error),
            "error_type": "unknown",
            "http_status": None,
            "retry_after": None,
            "quota_info": None,
        }

        if isinstance(error, HttpError):
            error_details["http_status"] = error.resp.status
            error_details["error_message"] = error._get_reason()

            # Extract retry-after header if present
            if error.resp.get("retry-after"):
                error_details["retry_after"] = int(error.resp.get("retry-after"))

            # Extract quota information from error details
            try:
                error_content = error.error_details if hasattr(error, 'error_details') else {}
                if isinstance(error_content, dict) and "errors" in error_content:
                    error_details["quota_info"] = error_content.get("errors", [])
            except:
                pass

            # Classify based on HTTP status and error message
            status = error.resp.status
            reason = error_details["error_message"].lower()

            if status == 401:
                if "invalid credentials" in reason or "token expired" in reason:
                    return GmailErrorType.AUTH_TOKEN_EXPIRED, error_details
                elif "disabled" in reason:
                    return GmailErrorType.AUTH_USER_DISABLED, error_details
                else:
                    return GmailErrorType.AUTH_TOKEN_REVOKED, error_details

            elif status == 403:
                if "quota" in reason or "rate limit" in reason:
                    if "daily" in reason:
                        return GmailErrorType.DAILY_QUOTA_EXCEEDED, error_details
                    elif "user" in reason:
                        return GmailErrorType.USER_QUOTA_EXCEEDED, error_details
                    else:
                        return GmailErrorType.RATE_LIMIT_EXCEEDED, error_details
                elif "insufficient" in reason or "scope" in reason:
                    return GmailErrorType.AUTH_INSUFFICIENT_SCOPES, error_details

            elif status == 404:
                if "recipient" in reason or "not found" in reason:
                    return GmailErrorType.RECIPIENT_NOT_FOUND, error_details

            elif status == 422:
                if "mailbox full" in reason:
                    return GmailErrorType.RECIPIENT_MAILBOX_FULL, error_details
                elif "rejected" in reason:
                    return GmailErrorType.RECIPIENT_REJECTED, error_details
                elif "spam" in reason:
                    return GmailErrorType.SPAM_DETECTED, error_details
                else:
                    return GmailErrorType.VALIDATION_ERROR, error_details

            elif status == 429:
                return GmailErrorType.RATE_LIMIT_EXCEEDED, error_details

            elif status == 500:
                return GmailErrorType.INTERNAL_SERVER_ERROR, error_details

            elif status == 503:
                return GmailErrorType.SERVICE_UNAVAILABLE, error_details

        # Check for specific error messages in non-HTTP errors
        error_str = str(error).lower()

        if "timeout" in error_str or "timed out" in error_str:
            return GmailErrorType.NETWORK_TIMEOUT, error_details
        elif "size" in error_str or "too large" in error_str:
            return GmailErrorType.MESSAGE_TOO_LARGE, error_details
        elif "domain" in error_str and "not found" in error_str:
            return GmailErrorType.RECIPIENT_DOMAIN_NOT_FOUND, error_details

        return GmailErrorType.UNKNOWN_ERROR, error_details

    def determine_recovery_action(
        self,
        error_type: GmailErrorType,
        error_details: Dict[str, Any],
        attempt: int
    ) -> Tuple[RecoveryAction, Optional[float], Optional[str]]:
        """Determine the best recovery action for an error."""

        # Update error statistics
        self.error_stats[error_type.value] = self.error_stats.get(error_type.value, 0) + 1

        # Check circuit breaker
        if self.circuit_breaker_state == "OPEN":
            reset_time = self._check_circuit_breaker_reset()
            if reset_time > 0:
                return RecoveryAction.PAUSE_SENDING, reset_time, "Circuit breaker open"

        # Determine action based on error type
        if error_type in [
            GmailErrorType.RATE_LIMIT_EXCEEDED,
            GmailErrorType.SERVICE_UNAVAILABLE,
            GmailErrorType.INTERNAL_SERVER_ERROR,
            GmailErrorType.NETWORK_TIMEOUT,
        ]:
            # Transient errors - retry with backoff
            if attempt < self.max_retries:
                delay = self._calculate_backoff(attempt, error_details.get("retry_after"))
                return RecoveryAction.RETRY_WITH_BACKOFF, delay, f"Transient error, retrying with {delay}s delay"
            else:
                return RecoveryAction.QUEUE_FOR_LATER, None, "Max retries exceeded, queuing for later"

        elif error_type in [
            GmailErrorType.AUTH_TOKEN_EXPIRED,
            GmailErrorType.AUTH_TOKEN_REVOKED,
        ]:
            # Authentication errors - refresh token
            return RecoveryAction.REFRESH_TOKEN, None, "Authentication token needs refresh"

        elif error_type == GmailErrorType.DAILY_QUOTA_EXCEEDED:
            # Daily quota exceeded - pause until next day
            return RecoveryAction.PAUSE_SENDING, 86400, "Daily quota exceeded, pausing for 24 hours"

        elif error_type == GmailErrorType.USER_QUOTA_EXCEEDED:
            # User quota exceeded - pause for shorter period
            return RecoveryAction.PAUSE_SENDING, 3600, "User quota exceeded, pausing for 1 hour"

        elif error_type in [
            GmailErrorType.RECIPIENT_NOT_FOUND,
            GmailErrorType.RECIPIENT_DOMAIN_NOT_FOUND,
            GmailErrorType.RECIPIENT_REJECTED,
        ]:
            # Permanent recipient errors - skip permanently
            return RecoveryAction.SKIP_PERMANENTLY, None, "Permanent recipient error, skipping email"

        elif error_type == GmailErrorType.RECIPIENT_MAILBOX_FULL:
            # Temporary recipient issue - queue for later
            return RecoveryAction.QUEUE_FOR_LATER, None, "Recipient mailbox full, queuing for later"

        elif error_type in [
            GmailErrorType.MESSAGE_TOO_LARGE,
            GmailErrorType.SPAM_DETECTED,
            GmailErrorType.MALFORMED_MESSAGE,
        ]:
            # Content errors - needs human intervention
            return RecoveryAction.REQUIRE_HUMAN_INTERVENTION, None, "Content error needs manual review"

        elif error_type == GmailErrorType.AUTH_INSUFFICIENT_SCOPES:
            # Configuration error - update scopes
            return RecoveryAction.UPDATE_CONFIGURATION, None, "Insufficient OAuth scopes, update configuration"

        else:
            # Unknown or other errors - retry with backoff up to limit, then queue
            if attempt < self.max_retries:
                delay = self._calculate_backoff(attempt)
                return RecoveryAction.RETRY_WITH_BACKOFF, delay, f"Unknown error, retrying with {delay}s delay"
            else:
                return RecoveryAction.QUEUE_FOR_LATER, None, "Unknown error, max retries exceeded"

    def _calculate_backoff(self, attempt: int, retry_after: Optional[int] = None) -> float:
        """Calculate backoff delay with exponential backoff and jitter."""
        if retry_after:
            # Use server-suggested retry-after if provided
            return float(retry_after)

        # Exponential backoff: base_delay * 2^(attempt-1)
        backoff = self.base_delay * (2 ** (attempt - 1))

        # Add jitter (±20%)
        import random
        jitter = random.uniform(0.8, 1.2)

        return backoff * jitter

    def update_circuit_breaker(self, success: bool) -> None:
        """Update circuit breaker state based on operation success."""
        if not success:
            self.circuit_breaker_failures += 1
            if self.circuit_breaker_failures >= self.circuit_breaker_threshold:
                self.circuit_breaker_state = "OPEN"
                self.circuit_breaker_opened_at = datetime.now(timezone.utc)
                logger.warning(f"Circuit breaker OPENED after {self.circuit_breaker_failures} failures")
        else:
            if self.circuit_breaker_state == "HALF_OPEN":
                # Success in half-open state, close circuit
                self.circuit_breaker_state = "CLOSED"
                self.circuit_breaker_failures = 0
                logger.info("Circuit breaker CLOSED after successful operation")
            elif self.circuit_breaker_state == "CLOSED":
                # Reset failure count on success
                self.circuit_breaker_failures = max(0, self.circuit_breaker_failures - 1)

    def _check_circuit_breaker_reset(self) -> float:
        """Check if circuit breaker should reset and return remaining time."""
        if self.circuit_breaker_state != "OPEN":
            return 0

        if not hasattr(self, 'circuit_breaker_opened_at'):
            self.circuit_breaker_state = "CLOSED"
            return 0

        time_open = (datetime.now(timezone.utc) - self.circuit_breaker_opened_at).total_seconds()

        if time_open >= self.circuit_breaker_reset_timeout:
            # Move to half-open state
            self.circuit_breaker_state = "HALF_OPEN"
            logger.info("Circuit breaker moved to HALF_OPEN state")
            return 0
        else:
            # Return remaining time until reset
            return self.circuit_breaker_reset_timeout - time_open

    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics and circuit breaker status."""
        return {
            "error_counts": self.error_stats,
            "circuit_breaker": {
                "state": self.circuit_breaker_state,
                "failure_count": self.circuit_breaker_failures,
                "threshold": self.circuit_breaker_threshold,
            },
            "total_errors": sum(self.error_stats.values()),
        }

    def should_attempt_send(self) -> Tuple[bool, Optional[str]]:
        """Check if sending should be attempted based on circuit breaker."""
        if self.circuit_breaker_state == "OPEN":
            reset_time = self._check_circuit_breaker_reset()
            if reset_time > 0:
                return False, f"Circuit breaker open, retry in {reset_time:.0f}s"
            else:
                # Moved to half-open, allow one attempt
                return True, "Circuit breaker half-open, attempting one send"

        return True, None


class EnhancedGmailService:
    """Gmail service with enhanced error handling."""

    def __init__(self, gmail_service, error_handler: GmailErrorHandler):
        self.gmail_service = gmail_service
        self.error_handler = error_handler
        self.retry_queue = []

    async def send_email_with_recovery(
        self,
        recipient: str,
        subject: str,
        body_text: str,
        body_html: str = "",
        user_id: str = "default_user"
    ) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
        """Send email with comprehensive error recovery."""

        # Check circuit breaker
        should_send, reason = self.error_handler.should_attempt_send()
        if not should_send:
            return None, "CIRCUIT_BREAKER_OPEN", {"reason": reason}

        attempt = 1
        last_error = None
        error_details = {}

        while attempt <= self.error_handler.max_retries:
            try:
                logger.info(f"Attempt {attempt}/{self.error_handler.max_retries} to send email to {recipient}")

                # Attempt to send email
                message_id = self.gmail_service.safe_send_email(
                    recipient=recipient,
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html,
                    user_id=user_id,
                )

                # Update circuit breaker on success
                self.error_handler.update_circuit_breaker(True)

                logger.info(f"Email sent successfully to {recipient}, message ID: {message_id}")
                return message_id, None, {"attempts": attempt}

            except Exception as e:
                last_error = e

                # Classify error
                error_type, error_details = self.error_handler.classify_error(e)
                logger.warning(f"Send attempt {attempt} failed: {error_type.value} - {error_details['error_message']}")

                # Determine recovery action
                recovery_action, delay, recovery_reason = self.error_handler.determine_recovery_action(
                    error_type, error_details, attempt
                )

                # Update circuit breaker on failure
                self.error_handler.update_circuit_breaker(False)

                # Execute recovery action
                if recovery_action == RecoveryAction.RETRY_WITH_BACKOFF:
                    if delay:
                        logger.info(f"Waiting {delay:.1f}s before retry: {recovery_reason}")
                        time.sleep(delay)
                    attempt += 1
                    continue

                elif recovery_action == RecoveryAction.REFRESH_TOKEN:
                    logger.info("Attempting token refresh")
                    # In a real implementation, refresh the OAuth token here
                    attempt += 1
                    continue

                elif recovery_action == RecoveryAction.QUEUE_FOR_LATER:
                    logger.info(f"Queuing email for later: {recovery_reason}")
                    self._add_to_retry_queue(recipient, subject, body_text, body_html, user_id)
                    return None, "QUEUED_FOR_LATER", {
                        "reason": recovery_reason,
                        "error_type": error_type.value,
                        "attempts": attempt,
                    }

                elif recovery_action == RecoveryAction.SKIP_PERMANENTLY:
                    logger.warning(f"Skipping email permanently: {recovery_reason}")
                    return None, "SKIPPED_PERMANENTLY", {
                        "reason": recovery_reason,
                        "error_type": error_type.value,
                        "attempts": attempt,
                    }

                elif recovery_action == RecoveryAction.PAUSE_SENDING:
                    logger.warning(f"Pausing sending: {recovery_reason}")
                    if delay:
                        logger.info(f"Pausing for {delay:.0f} seconds")
                    return None, "PAUSED_SENDING", {
                        "reason": recovery_reason,
                        "pause_duration": delay,
                        "error_type": error_type.value,
                        "attempts": attempt,
                    }

                elif recovery_action == RecoveryAction.REQUIRE_HUMAN_INTERVENTION:
                    logger.error(f"Human intervention required: {recovery_reason}")
                    return None, "HUMAN_INTERVENTION_REQUIRED", {
                        "reason": recovery_reason,
                        "error_type": error_type.value,
                        "attempts": attempt,
                    }

                elif recovery_action == RecoveryAction.UPDATE_CONFIGURATION:
                    logger.error(f"Configuration update required: {recovery_reason}")
                    return None, "CONFIGURATION_UPDATE_REQUIRED", {
                        "reason": recovery_reason,
                        "error_type": error_type.value,
                        "attempts": attempt,
                    }

        # If we get here, all retries failed
        logger.error(f"All {self.error_handler.max_retries} attempts failed for {recipient}")
        return None, "ALL_RETRIES_FAILED", {
            "error": str(last_error),
            "error_type": error_details.get("error_type", "unknown"),
            "attempts": attempt,
        }

    def _add_to_retry_queue(
        self,
        recipient: str,
        subject: str,
        body_text: str,
        body_html: str,
        user_id: str
    ) -> None:
        """Add email to retry queue for later sending."""
        queue_entry = {
            "recipient": recipient,
            "subject": subject,
            "body_text": body_text,
            "body_html": body_html,
            "user_id": user_id,
            "added_at": datetime.now(timezone.utc).isoformat(),
            "retry_count": 0,
            "last_attempt": None,
            "next_retry": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        }
        self.retry_queue.append(queue_entry)
        logger.info(f"Added email to retry queue for {recipient}")

    def process_retry_queue(self) -> Dict[str, Any]:
        """Process emails in the retry queue."""
        results = {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "still_queued": 0,
        }

        current_time = datetime.now(timezone.utc)
        new_queue = []

        for entry in self.retry_queue:
            # Check if it's time to retry
            next_retry = datetime.fromisoformat(entry["next_retry"].replace('Z', '+00:00'))

            if current_time >= next_retry and entry["retry_count"] < 3:
                # Attempt to resend
                try:
                    message_id = self.gmail_service.safe_send_email(
                        recipient=entry["recipient"],
                        subject=entry["subject"],
                        body_text=entry["body_text"],
                        body_html=entry["body_html"],
                        user_id=entry["user_id"],
                    )

                    results["successful"] += 1
                    logger.info(f"Retry successful for {entry['recipient']}")

                except Exception as e:
                    # Update retry entry
                    entry["retry_count"] += 1
                    entry["last_attempt"] = current_time.isoformat()
                    entry["next_retry"] = (current_time + timedelta(hours=entry["retry_count"])).isoformat()
                    entry["last_error"] = str(e)

                    if entry["retry_count"] >= 3:
                        results["failed"] += 1
                        logger.error(f"Permanent failure for {entry['recipient']} after 3 retries")
                    else:
                        new_queue.append(entry)
                        results["still_queued"] += 1
                        logger.warning(f"Retry failed for {entry['recipient']}, will retry later")

                results["processed"] += 1
            else:
                # Not time to retry yet
                new_queue.append(entry)
                results["still_queued"] += 1

        self.retry_queue = new_queue
        return results