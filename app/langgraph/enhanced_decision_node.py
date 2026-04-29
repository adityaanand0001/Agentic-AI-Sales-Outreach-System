"""Enhanced Decision Node with comprehensive Gmail error handling."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.services.mail_tracker import MailTrackerService
from app.services.gmail_oauth import GmailOAuthService
from supabase import Client

logger = logging.getLogger(__name__)


class IndustrialDecisionNode:
    """Industrial-grade decision node merging safety, context, and error recovery."""

    def __init__(self, tracker: MailTrackerService, gmail: GmailOAuthService, db: Client):
        self.tracker = tracker
        self.gmail = gmail
        self.db = db
        from app.config.settings import get_settings
        self.settings = get_settings()

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Make final decision with combined safety and error handling."""
        logger.info("Making industrial decision with safety checks and error recovery")

        confidence = state.get("ai_confidence", 0.0)
        requires_human = state.get("requires_human", True)
        
        # 1. Respect Global Safety Switch (from Basic Node)
        if not self.settings.send_email_directly:
            logger.info("Global send switch is OFF. Forcing human review.")
            requires_human = True

        try:
            # 2. Create tracker record WITH FULL CONTEXT (fixed from Enhanced Node)
            tracker_record = self.tracker.create_record(
                company_name=state.get("company_name", ""),
                email=state.get("email", ""),
                subject=state.get("email_subject", ""),
                body_preview=state.get("email_body", ""), # Removed 500-char limit
                context=state.get("context", ""),        # Restored missing context
                status="PENDING",
            )

            tracker_id = tracker_record["id"]
            state["tracker_id"] = tracker_id

            # 3. Decision Logic
            auto_send_threshold = self.settings.auto_send_threshold
            
            if not requires_human and confidence >= auto_send_threshold:
                # Auto-send with enhanced error handling
                return self._enhanced_auto_send(state, tracker_id)
            elif requires_human:
                # Send to human review
                return self._human_review_decision(state, tracker_id, confidence)
            else:
                # Low confidence, skip
                return self._skip_decision(state, tracker_id)

        except Exception as e:
            logger.error(f"Industrial decision failed: {e}")
            return self._handle_critical_error(state, str(e))

    def _enhanced_auto_send(self, state: Dict[str, Any], tracker_id: str) -> Dict[str, Any]:
        """Auto-send with enhanced error handling."""
        try:
            # Use enhanced send email with comprehensive error recovery
            message_id, error_code, error_details = self.gmail.enhanced_send_email(
                recipient=state.get("email", ""),
                subject=state.get("email_subject", ""),
                body_text=state.get("email_body", ""),
            )

            if message_id:
                # Success - email sent
                self.tracker.update_status(
                    tracker_id,
                    "SENT",
                    gmail_message_id=message_id,
                )

                self._log_ai_decision(
                    tracker_id=tracker_id,
                    decision_type="AUTO_APPROVAL",
                    confidence=state.get("ai_confidence", 0.0),
                    error_code=None,
                    error_details=None,
                )

                return {
                    **state,
                    "gmail_message_id": message_id,
                    "action_taken": "AUTO_SENT",
                    "processing_stage": "DECISION_MADE",
                    "error_code": None,
                    "error_details": None,
                }

            else:
                # Enhanced error handling provided recovery information
                return self._handle_enhanced_error(
                    state, tracker_id, error_code, error_details
                )

        except Exception as e:
            # Fallback to basic error handling if enhanced fails
            logger.error(f"Enhanced auto-send failed: {e}")
            return self._handle_basic_error(state, tracker_id, str(e))

    def _handle_enhanced_error(
        self,
        state: Dict[str, Any],
        tracker_id: str,
        error_code: Optional[str],
        error_details: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle errors from enhanced email sending."""
        error_message = error_details.get("reason", "Unknown error")

        # Map error codes to appropriate actions
        if error_code in ["QUEUED_FOR_LATER", "PAUSED_SENDING"]:
            # Temporary issue - move to human review for manual handling
            logger.info(f"Email queued/paused: {error_message}")
            return self._move_to_error_review(state, tracker_id, error_code, error_details)

        elif error_code in ["SKIPPED_PERMANENTLY", "HUMAN_INTERVENTION_REQUIRED"]:
            # Permanent or serious issue - mark as failed with details
            logger.warning(f"Email permanently skipped: {error_message}")
            return self._mark_as_failed_with_details(
                state, tracker_id, error_code, error_details
            )

        elif error_code in ["CONFIGURATION_UPDATE_REQUIRED", "ALL_RETRIES_FAILED"]:
            # System issue - needs attention
            logger.error(f"System issue detected: {error_message}")
            return self._mark_as_system_error(state, tracker_id, error_code, error_details)

        elif error_code == "CIRCUIT_BREAKER_OPEN":
            # Circuit breaker active - pause processing
            logger.warning(f"Circuit breaker open: {error_message}")
            return self._handle_circuit_breaker(state, tracker_id, error_details)

        else:
            # Unknown error code
            logger.error(f"Unknown error code: {error_code}")
            return self._mark_as_failed_with_details(
                state, tracker_id, error_code or "UNKNOWN_ERROR", error_details
            )

    def _move_to_error_review(
        self,
        state: Dict[str, Any],
        tracker_id: str,
        error_code: str,
        error_details: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Move email to error review queue."""
        now = datetime.now(timezone.utc).isoformat()

        review_entry = {
            "tracker_id": tracker_id,
            "reason": f"Temporary sending issue: {error_details.get('reason', 'Unknown')}",
            "error_code": error_code,
            "error_details": error_details,
            "priority": 90,  # High priority for error review
            "status": "ERROR_REVIEW",
            "created_at": now,
            "updated_at": now,
        }

        # Create special error review queue entry
        self.db.table("error_review_queue").insert(review_entry).execute()

        # Update tracker status
        self.tracker.update_status(
            tracker_id,
            "ERROR_REVIEW",
            error=error_details.get("reason", "Temporary sending issue"),
        )

        # Log AI decision with error info
        self._log_ai_decision(
            tracker_id=tracker_id,
            decision_type="AUTO_APPROVAL_ERROR",
            confidence=state.get("ai_confidence", 0.0),
            error_code=error_code,
            error_details=error_details,
        )

        return {
            **state,
            "action_taken": "ERROR_REVIEW",
            "processing_stage": "DECISION_MADE",
            "error_code": error_code,
            "error_details": error_details,
        }

    def _mark_as_failed_with_details(
        self,
        state: Dict[str, Any],
        tracker_id: str,
        error_code: str,
        error_details: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Mark email as failed with detailed error information."""
        error_message = error_details.get("reason", "Permanent sending failure")

        self.tracker.update_status(
            tracker_id,
            "FAILED",
            error=error_message,
            gmail_message_id=None,
        )

        # Log detailed error information
        self._log_error_details(tracker_id, error_code, error_details)

        self._log_ai_decision(
            tracker_id=tracker_id,
            decision_type="AUTO_APPROVAL_FAILED",
            confidence=state.get("ai_confidence", 0.0),
            error_code=error_code,
            error_details=error_details,
        )

        return {
            **state,
            "action_taken": "FAILED",
            "processing_stage": "DECISION_MADE",
            "error_code": error_code,
            "error_details": error_details,
        }

    def _mark_as_system_error(
        self,
        state: Dict[str, Any],
        tracker_id: str,
        error_code: str,
        error_details: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Mark as system error requiring administrative attention."""
        error_message = error_details.get("reason", "System configuration issue")

        # Update tracker with system error flag
        self.tracker.update_status(
            tracker_id,
            "SYSTEM_ERROR",
            error=error_message,
            gmail_message_id=None,
        )

        # Create system alert
        self._create_system_alert(tracker_id, error_code, error_details)

        self._log_ai_decision(
            tracker_id=tracker_id,
            decision_type="SYSTEM_ERROR",
            confidence=state.get("ai_confidence", 0.0),
            error_code=error_code,
            error_details=error_details,
        )

        return {
            **state,
            "action_taken": "SYSTEM_ERROR",
            "processing_stage": "DECISION_MADE",
            "error_code": error_code,
            "error_details": error_details,
        }

    def _handle_circuit_breaker(
        self,
        state: Dict[str, Any],
        tracker_id: str,
        error_details: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle circuit breaker scenario."""
        pause_reason = error_details.get("reason", "Circuit breaker active")

        # Update tracker
        self.tracker.update_status(
            tracker_id,
            "PAUSED",
            error=pause_reason,
        )

        # Create circuit breaker alert
        self._create_circuit_breaker_alert(tracker_id, error_details)

        self._log_ai_decision(
            tracker_id=tracker_id,
            decision_type="CIRCUIT_BREAKER",
            confidence=state.get("ai_confidence", 0.0),
            error_code="CIRCUIT_BREAKER_OPEN",
            error_details=error_details,
        )

        return {
            **state,
            "action_taken": "PAUSED",
            "processing_stage": "DECISION_MADE",
            "error_code": "CIRCUIT_BREAKER_OPEN",
            "error_details": error_details,
        }

    def _handle_basic_error(
        self,
        state: Dict[str, Any],
        tracker_id: str,
        error_message: str
    ) -> Dict[str, Any]:
        """Handle basic errors (fallback)."""
        logger.error(f"Basic error handling: {error_message}")

        self.tracker.update_status(
            tracker_id,
            "FAILED",
            error=error_message,
        )

        self._log_ai_decision(
            tracker_id=tracker_id,
            decision_type="AUTO_APPROVAL_FAILED",
            confidence=state.get("ai_confidence", 0.0),
            error_code="BASIC_ERROR",
            error_details={"error_message": error_message},
        )

        return {
            **state,
            "action_taken": "FAILED",
            "processing_stage": "DECISION_MADE",
            "error": error_message,
            "error_code": "BASIC_ERROR",
        }

    def _handle_critical_error(self, state: Dict[str, Any], error_message: str) -> Dict[str, Any]:
        """Handle critical errors in the decision process."""
        logger.critical(f"Critical decision error: {error_message}")

        return {
            **state,
            "action_taken": "CRITICAL_ERROR",
            "processing_stage": "DECISION_MADE",
            "error": error_message,
            "error_code": "CRITICAL_ERROR",
        }

    def _human_review_decision(
        self,
        state: Dict[str, Any],
        tracker_id: str,
        confidence: float
    ) -> Dict[str, Any]:
        """Handle human review decision."""
        now = datetime.now(timezone.utc).isoformat()

        reason = "Low AI confidence"
        if confidence < 0.5:
            reason = "Very low confidence - needs human evaluation"
        elif confidence < 0.7:
            reason = "Moderate confidence - recommend review"

        review_entry = {
            "tracker_id": tracker_id,
            "reason": reason,
            "priority": int(100 - (confidence * 100)),
            "status": "PENDING",
            "created_at": now,
            "updated_at": now,
        }

        self.db.table("human_review_queue").insert(review_entry).execute()

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

    def _skip_decision(self, state: Dict[str, Any], tracker_id: str) -> Dict[str, Any]:
        """Handle skip decision."""
        self.tracker.update_status(
            tracker_id,
            "REJECTED",
            error="Low AI confidence - skipped",
        )

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

    # ── Utility Methods ────────────────────────────────────────────────────────────

    def _log_ai_decision(
        self,
        tracker_id: str,
        decision_type: str,
        confidence: float,
        error_code: Optional[str] = None,
        error_details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log AI decision with optional error information."""
        now = datetime.now(timezone.utc).isoformat()

        decision_entry = {
            "tracker_id": tracker_id,
            "decision_type": decision_type,
            "confidence": confidence,
            "model_used": self.settings.llm_model,
            "created_at": now,
        }

        if error_code:
            decision_entry["error_code"] = error_code

        if error_details:
            decision_entry["error_details"] = error_details

        self.db.table("ai_decisions").insert(decision_entry).execute()

    def _log_error_details(
        self,
        tracker_id: str,
        error_code: str,
        error_details: Dict[str, Any]
    ) -> None:
        """Log detailed error information."""
        now = datetime.now(timezone.utc).isoformat()

        error_entry = {
            "tracker_id": tracker_id,
            "error_code": error_code,
            "error_details": error_details,
            "created_at": now,
        }

        self.db.table("error_logs").insert(error_entry).execute()

    def _create_system_alert(
        self,
        tracker_id: str,
        error_code: str,
        error_details: Dict[str, Any]
    ) -> None:
        """Create system alert for administrative attention."""
        now = datetime.now(timezone.utc).isoformat()

        alert_entry = {
            "tracker_id": tracker_id,
            "alert_type": "SYSTEM_ERROR",
            "error_code": error_code,
            "error_details": error_details,
            "priority": 100,  # Highest priority
            "status": "PENDING",
            "created_at": now,
        }

        self.db.table("system_alerts").insert(alert_entry).execute()

    def _create_circuit_breaker_alert(
        self,
        tracker_id: str,
        error_details: Dict[str, Any]
    ) -> None:
        """Create alert for circuit breaker activation."""
        now = datetime.now(timezone.utc).isoformat()

        alert_entry = {
            "tracker_id": tracker_id,
            "alert_type": "CIRCUIT_BREAKER",
            "error_details": error_details,
            "priority": 90,
            "status": "PENDING",
            "created_at": now,
        }

        self.db.table("system_alerts").insert(alert_entry).execute()