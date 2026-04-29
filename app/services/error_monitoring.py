"""Monitoring and alerting for Gmail API errors."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from supabase import Client

logger = logging.getLogger(__name__)


class ErrorMonitor:
    """Monitor error patterns and generate alerts."""

    def __init__(self, db: Client):
        self.db = db
        self.alert_thresholds = {
            "rate_limit": 10,      # 10 rate limit errors per hour
            "auth_errors": 5,      # 5 auth errors per hour
            "quota_exceeded": 1,   # 1 quota exceeded error
            "circuit_breaker": 1,  # 1 circuit breaker activation
            "system_error": 1,     # 1 system error
        }

    def analyze_error_patterns(self, hours: int = 24) -> Dict[str, Any]:
        """Analyze error patterns over the specified time period."""
        try:
            start_time = datetime.now(timezone.utc) - timedelta(hours=hours)

            # Get error logs from the specified period
            resp = self.db.table("error_logs").select("*").gte("created_at", start_time.isoformat()).execute()
            error_logs = resp.data or []

            # Get system alerts
            alert_resp = self.db.table("system_alerts").select("*").gte("created_at", start_time.isoformat()).execute()
            system_alerts = alert_resp.data or []

            # Analyze error patterns
            error_counts = self._count_errors_by_type(error_logs)
            alert_counts = self._count_alerts_by_type(system_alerts)

            # Calculate error rates
            total_errors = sum(error_counts.values())
            error_rate_per_hour = total_errors / hours if hours > 0 else 0

            # Identify patterns
            patterns = self._identify_patterns(error_logs, error_counts)

            # Check thresholds
            threshold_violations = self._check_thresholds(error_counts, alert_counts, hours)

            return {
                "analysis_period": {
                    "start": start_time.isoformat(),
                    "end": datetime.now(timezone.utc).isoformat(),
                    "hours": hours,
                },
                "error_statistics": {
                    "total_errors": total_errors,
                    "error_rate_per_hour": round(error_rate_per_hour, 2),
                    "error_counts_by_type": error_counts,
                    "unique_error_codes": len(set(log.get("error_code") for log in error_logs)),
                },
                "alert_statistics": {
                    "total_alerts": len(system_alerts),
                    "alert_counts_by_type": alert_counts,
                    "unresolved_alerts": len([a for a in system_alerts if a.get("status") != "RESOLVED"]),
                },
                "patterns_detected": patterns,
                "threshold_violations": threshold_violations,
                "recommendations": self._generate_recommendations(
                    error_counts, alert_counts, patterns, threshold_violations
                ),
            }

        except Exception as e:
            logger.error(f"Failed to analyze error patterns: {e}")
            return {"error": str(e)}

    def _count_errors_by_type(self, error_logs: List[Dict[str, Any]]) -> Dict[str, int]:
        """Count errors by error code."""
        counts = {}
        for log in error_logs:
            error_code = log.get("error_code", "UNKNOWN")
            counts[error_code] = counts.get(error_code, 0) + 1
        return counts

    def _count_alerts_by_type(self, alerts: List[Dict[str, Any]]) -> Dict[str, int]:
        """Count alerts by alert type."""
        counts = {}
        for alert in alerts:
            alert_type = alert.get("alert_type", "UNKNOWN")
            counts[alert_type] = counts.get(alert_type, 0) + 1
        return counts

    def _identify_patterns(
        self, error_logs: List[Dict[str, Any]], error_counts: Dict[str, int]
    ) -> List[Dict[str, Any]]:
        """Identify patterns in error logs."""
        patterns = []

        # Group errors by hour
        errors_by_hour = {}
        for log in error_logs:
            created_at = log.get("created_at")
            if created_at:
                hour = created_at[:13]  # YYYY-MM-DDTHH
                if hour not in errors_by_hour:
                    errors_by_hour[hour] = []
                errors_by_hour[hour].append(log)

        # Check for increasing error rates
        hours = sorted(errors_by_hour.keys())
        if len(hours) >= 3:
            error_counts_by_hour = [len(errors_by_hour[h]) for h in hours]
            if self._is_increasing(error_counts_by_hour):
                patterns.append({
                    "type": "INCREASING_ERROR_RATE",
                    "description": "Error rate is increasing over time",
                    "severity": "HIGH",
                    "data": {
                        "hours": hours[-3:],
                        "error_counts": error_counts_by_hour[-3:],
                        "trend": "increasing",
                    }
                })

        # Check for specific error code patterns
        for error_code, count in error_counts.items():
            if count >= 5:  # Threshold for pattern detection
                # Check if errors are clustered in time
                error_times = [
                    log.get("created_at")
                    for log in error_logs
                    if log.get("error_code") == error_code
                ]
                if len(error_times) >= 3:
                    time_diffs = self._calculate_time_differences(error_times)
                    avg_diff = sum(time_diffs) / len(time_diffs) if time_diffs else 0

                    if avg_diff < 3600:  # Less than 1 hour between errors
                        patterns.append({
                            "type": "ERROR_CLUSTER",
                            "description": f"Multiple '{error_code}' errors clustered in time",
                            "severity": "MEDIUM",
                            "data": {
                                "error_code": error_code,
                                "count": count,
                                "avg_time_between_errors_seconds": round(avg_diff, 1),
                            }
                        })

        # Check for authentication error patterns
        auth_errors = ["AUTH_TOKEN_EXPIRED", "AUTH_TOKEN_REVOKED", "AUTH_INSUFFICIENT_SCOPES"]
        auth_error_count = sum(error_counts.get(code, 0) for code in auth_errors)
        if auth_error_count >= 3:
            patterns.append({
                "type": "AUTHENTICATION_ISSUES",
                "description": "Multiple authentication errors detected",
                "severity": "HIGH",
                "data": {
                    "total_auth_errors": auth_error_count,
                    "error_codes": [code for code in auth_errors if error_counts.get(code, 0) > 0],
                }
            })

        return patterns

    def _check_thresholds(
        self,
        error_counts: Dict[str, int],
        alert_counts: Dict[str, int],
        hours: int
    ) -> List[Dict[str, Any]]:
        """Check if error thresholds are violated."""
        violations = []

        # Check rate limit errors
        rate_limit_errors = error_counts.get("RATE_LIMIT_EXCEEDED", 0)
        if rate_limit_errors > self.alert_thresholds["rate_limit"]:
            violations.append({
                "type": "RATE_LIMIT_THRESHOLD",
                "description": f"Rate limit errors exceeded threshold: {rate_limit_errors} > {self.alert_thresholds['rate_limit']}",
                "severity": "MEDIUM",
                "data": {
                    "threshold": self.alert_thresholds["rate_limit"],
                    "actual": rate_limit_errors,
                    "period_hours": hours,
                }
            })

        # Check authentication errors
        auth_errors = sum(
            error_counts.get(code, 0)
            for code in ["AUTH_TOKEN_EXPIRED", "AUTH_TOKEN_REVOKED", "AUTH_INSUFFICIENT_SCOPES"]
        )
        if auth_errors > self.alert_thresholds["auth_errors"]:
            violations.append({
                "type": "AUTH_ERROR_THRESHOLD",
                "description": f"Authentication errors exceeded threshold: {auth_errors} > {self.alert_thresholds['auth_errors']}",
                "severity": "HIGH",
                "data": {
                    "threshold": self.alert_thresholds["auth_errors"],
                    "actual": auth_errors,
                    "period_hours": hours,
                }
            })

        # Check quota exceeded errors
        quota_errors = error_counts.get("DAILY_QUOTA_EXCEEDED", 0)
        if quota_errors > self.alert_thresholds["quota_exceeded"]:
            violations.append({
                "type": "QUOTA_THRESHOLD",
                "description": f"Quota exceeded errors detected: {quota_errors}",
                "severity": "HIGH",
                "data": {
                    "threshold": self.alert_thresholds["quota_exceeded"],
                    "actual": quota_errors,
                }
            })

        # Check circuit breaker alerts
        circuit_alerts = alert_counts.get("CIRCUIT_BREAKER", 0)
        if circuit_alerts > self.alert_thresholds["circuit_breaker"]:
            violations.append({
                "type": "CIRCUIT_BREAKER_THRESHOLD",
                "description": f"Circuit breaker activated: {circuit_alerts} times",
                "severity": "HIGH",
                "data": {
                    "threshold": self.alert_thresholds["circuit_breaker"],
                    "actual": circuit_alerts,
                }
            })

        # Check system errors
        system_errors = alert_counts.get("SYSTEM_ERROR", 0)
        if system_errors > self.alert_thresholds["system_error"]:
            violations.append({
                "type": "SYSTEM_ERROR_THRESHOLD",
                "description": f"System errors detected: {system_errors}",
                "severity": "CRITICAL",
                "data": {
                    "threshold": self.alert_thresholds["system_error"],
                    "actual": system_errors,
                }
            })

        return violations

    def _generate_recommendations(
        self,
        error_counts: Dict[str, int],
        alert_counts: Dict[str, Any],
        patterns: List[Dict[str, Any]],
        violations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Generate recommendations based on error analysis."""
        recommendations = []

        # Rate limit recommendations
        if error_counts.get("RATE_LIMIT_EXCEEDED", 0) > 0:
            recommendations.append({
                "type": "RATE_LIMITING",
                "priority": "HIGH",
                "action": "Implement rate limiting with exponential backoff",
                "description": "Reduce sending frequency or implement smarter rate limiting",
                "details": {
                    "current_rate_limit_errors": error_counts.get("RATE_LIMIT_EXCEEDED", 0),
                    "suggested_backoff": "Exponential backoff with jitter",
                    "max_retries": "3 with increasing delays",
                }
            })

        # Authentication recommendations
        auth_errors = sum(
            error_counts.get(code, 0)
            for code in ["AUTH_TOKEN_EXPIRED", "AUTH_TOKEN_REVOKED", "AUTH_INSUFFICIENT_SCOPES"]
        )
        if auth_errors > 0:
            recommendations.append({
                "type": "AUTHENTICATION",
                "priority": "CRITICAL",
                "action": "Review and refresh authentication tokens",
                "description": "Authentication issues detected - check token validity and scopes",
                "details": {
                    "total_auth_errors": auth_errors,
                    "suggested_actions": [
                        "Check token expiration",
                        "Verify OAuth scopes",
                        "Implement token refresh logic",
                    ]
                }
            })

        # Quota recommendations
        if error_counts.get("DAILY_QUOTA_EXCEEDED", 0) > 0:
            recommendations.append({
                "type": "QUOTA_MANAGEMENT",
                "priority": "HIGH",
                "action": "Implement quota monitoring and management",
                "description": "Daily quota exceeded - consider spreading sends or requesting quota increase",
                "details": {
                    "quota_errors": error_counts.get("DAILY_QUOTA_EXCEEDED", 0),
                    "suggested_actions": [
                        "Monitor daily quota usage",
                        "Implement quota-aware scheduling",
                        "Request quota increase from Google",
                    ]
                }
            })

        # Circuit breaker recommendations
        if alert_counts.get("CIRCUIT_BREAKER", 0) > 0:
            recommendations.append({
                "type": "CIRCUIT_BREAKER",
                "priority": "HIGH",
                "action": "Review circuit breaker configuration",
                "description": "Circuit breaker activated - review error thresholds and reset times",
                "details": {
                    "circuit_breaker_activations": alert_counts.get("CIRCUIT_BREAKER", 0),
                    "suggested_actions": [
                        "Adjust circuit breaker thresholds",
                        "Review error patterns causing activations",
                        "Consider implementing fallback strategies",
                    ]
                }
            })

        # Pattern-based recommendations
        for pattern in patterns:
            if pattern["type"] == "INCREASING_ERROR_RATE":
                recommendations.append({
                    "type": "ERROR_TREND",
                    "priority": "MEDIUM",
                    "action": "Investigate increasing error rate trend",
                    "description": "Error rate is increasing over time - investigate root cause",
                    "details": pattern["data"]
                })

            elif pattern["type"] == "ERROR_CLUSTER":
                recommendations.append({
                    "type": "ERROR_CLUSTER",
                    "priority": "MEDIUM",
                    "action": f"Investigate clustered '{pattern['data']['error_code']}' errors",
                    "description": "Errors are clustered in time - may indicate systemic issue",
                    "details": pattern["data"]
                })

        return recommendations

    def _is_increasing(self, values: List[int]) -> bool:
        """Check if values are generally increasing."""
        if len(values) < 2:
            return False

        increasing_count = 0
        for i in range(1, len(values)):
            if values[i] > values[i-1]:
                increasing_count += 1

        # Consider increasing if at least 2/3 of comparisons show increase
        return increasing_count >= (len(values) - 1) * 2 // 3

    def _calculate_time_differences(self, timestamps: List[str]) -> List[float]:
        """Calculate time differences between consecutive timestamps."""
        diffs = []
        for i in range(1, len(timestamps)):
            try:
                t1 = datetime.fromisoformat(timestamps[i-1].replace('Z', '+00:00'))
                t2 = datetime.fromisoformat(timestamps[i].replace('Z', '+00:00'))
                diffs.append((t2 - t1).total_seconds())
            except:
                continue
        return diffs

    def create_alert(
        self,
        alert_type: str,
        error_code: Optional[str] = None,
        error_details: Optional[Dict[str, Any]] = None,
        priority: int = 50,
        tracker_id: Optional[str] = None
    ) -> Optional[str]:
        """Create a system alert."""
        try:
            now = datetime.now(timezone.utc).isoformat()

            alert_entry = {
                "alert_type": alert_type,
                "error_code": error_code,
                "error_details": error_details or {},
                "priority": priority,
                "status": "PENDING",
                "created_at": now,
                "updated_at": now,
            }

            if tracker_id:
                alert_entry["tracker_id"] = tracker_id

            resp = self.db.table("system_alerts").insert(alert_entry).execute()
            if resp.data:
                alert_id = resp.data[0]["id"]
                logger.info(f"Created alert {alert_id} of type {alert_type}")
                return alert_id

        except Exception as e:
            logger.error(f"Failed to create alert: {e}")

        return None

    def get_active_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get active (unresolved) alerts."""
        try:
            resp = (
                self.db.table("system_alerts")
                .select("*")
                .neq("status", "RESOLVED")
                .order("priority", desc=True)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(f"Failed to get active alerts: {e}")
            return []

    def resolve_alert(self, alert_id: str, resolved_by: str = "system") -> bool:
        """Mark an alert as resolved."""
        try:
            now = datetime.now(timezone.utc).isoformat()

            self.db.table("system_alerts").update({
                "status": "RESOLVED",
                "resolved_at": now,
                "updated_at": now,
            }).eq("id", alert_id).execute()

            logger.info(f"Alert {alert_id} resolved by {resolved_by}")
            return True

        except Exception as e:
            logger.error(f"Failed to resolve alert {alert_id}: {e}")
            return False

    def generate_daily_report(self) -> Dict[str, Any]:
        """Generate a daily error report."""
        try:
            # Analyze last 24 hours
            analysis = self.analyze_error_patterns(hours=24)

            # Get top error sources
            error_resp = self.db.table("error_logs").select("error_code, COUNT(*)").group("error_code").order("count", desc=True).limit(5).execute()
            top_errors = error_resp.data or []

            # Get unresolved alerts
            unresolved_alerts = self.get_active_alerts(limit=20)

            # Calculate success rate (estimate)
            tracker_resp = self.db.table("mail_agent_tracker").select("status, COUNT(*)").group("status").execute()
            tracker_stats = {item["status"]: item["count"] for item in (tracker_resp.data or [])}

            total_emails = sum(tracker_stats.values())
            successful_emails = tracker_stats.get("SENT", 0)
            success_rate = (successful_emails / total_emails * 100) if total_emails > 0 else 0

            report = {
                "report_date": datetime.now(timezone.utc).date().isoformat(),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "summary": {
                    "total_errors_last_24h": analysis.get("error_statistics", {}).get("total_errors", 0),
                    "error_rate_per_hour": analysis.get("error_statistics", {}).get("error_rate_per_hour", 0),
                    "unresolved_alerts": len(unresolved_alerts),
                    "estimated_success_rate": round(success_rate, 1),
                },
                "top_errors": top_errors,
                "patterns_detected": analysis.get("patterns_detected", []),
                "threshold_violations": analysis.get("threshold_violations", []),
                "recommendations": analysis.get("recommendations", []),
                "unresolved_alerts_preview": unresolved_alerts[:5],  # First 5
                "system_health": self._calculate_system_health(analysis, success_rate),
            }

            # Store report
            self._store_daily_report(report)

            return report

        except Exception as e:
            logger.error(f"Failed to generate daily report: {e}")
            return {"error": str(e)}

    def _calculate_system_health(
        self, analysis: Dict[str, Any], success_rate: float
    ) -> Dict[str, Any]:
        """Calculate system health score."""
        health_score = 100  # Start with perfect score

        # Deduct for errors
        total_errors = analysis.get("error_statistics", {}).get("total_errors", 0)
        health_score -= min(30, total_errors * 2)  # Max 30 point deduction

        # Deduct for error rate
        error_rate = analysis.get("error_statistics", {}).get("error_rate_per_hour", 0)
        health_score -= min(20, error_rate * 5)  # Max 20 point deduction

        # Deduct for unresolved alerts
        unresolved_alerts = analysis.get("alert_statistics", {}).get("unresolved_alerts", 0)
        health_score -= min(20, unresolved_alerts * 4)  # Max 20 point deduction

        # Adjust for success rate
        if success_rate < 80:
            health_score -= (80 - success_rate)  # 1 point per % below 80

        # Ensure score is between 0 and 100
        health_score = max(0, min(100, health_score))

        # Determine status
        if health_score >= 80:
            status = "HEALTHY"
        elif health_score >= 60:
            status = "DEGRADED"
        elif health_score >= 40:
            status = "UNHEALTHY"
        else:
            status = "CRITICAL"

        return {
            "score": round(health_score),
            "status": status,
            "factors": {
                "error_count_impact": min(30, total_errors * 2),
                "error_rate_impact": min(20, error_rate * 5),
                "alerts_impact": min(20, unresolved_alerts * 4),
                "success_rate_impact": max(0, 80 - success_rate),
            }
        }

    def _store_daily_report(self, report: Dict[str, Any]) -> None:
        """Store daily report in database."""
        try:
            report_entry = {
                "report_date": report["report_date"],
                "report_data": report,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            self.db.table("daily_reports").insert(report_entry).execute()
            logger.info(f"Stored daily report for {report['report_date']}")

        except Exception as e:
            logger.error(f"Failed to store daily report: {e}")