"""Analytics service for email performance insights."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config.database import get_supabase

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Aggregates email performance data from tracker, compliance, and other tables."""

    def __init__(self):
        self.db = get_supabase()
        self.tracker_table = "mail_agent_tracker"
        self.compliance_table = "mail_agent_compliance"
        self.follow_ups_table = "mail_agent_follow_ups"
        self.schedule_table = "mail_agent_schedule_queue"

    def get_volume_over_time(self, days: int = 30) -> list[dict]:
        """Daily send/fail volume for the last N days."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        resp = (
            self.db.table(self.tracker_table)
            .select("created_at,status")
            .gte("created_at", cutoff)
            .execute()
        )
        rows = resp.data or []
        daily = defaultdict(lambda: {"sent": 0, "failed": 0, "pending": 0, "rejected": 0})
        for r in rows:
            day = (r.get("created_at") or "")[:10]
            s = r.get("status", "")
            if s == "SENT":
                daily[day]["sent"] += 1
            elif s == "FAILED":
                daily[day]["failed"] += 1
            elif s == "PENDING":
                daily[day]["pending"] += 1
            elif s == "REJECTED":
                daily[day]["rejected"] += 1

        result = []
        for i in range(days - 1, -1, -1):
            d = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
            entry = {"date": d, **daily[d]}
            result.append(entry)
        return result

    def get_status_breakdown(self) -> dict:
        """Total counts per status."""
        resp = self.db.table(self.tracker_table).select("status").execute()
        rows = resp.data or []
        counts: dict[str, int] = {}
        for r in rows:
            s = r.get("status", "UNKNOWN")
            counts[s] = counts.get(s, 0) + 1
        return counts

    def get_compliance_breakdown(self) -> dict:
        """Compliance event counts by type."""
        resp = self.db.table(self.compliance_table).select("event_type").execute()
        rows = resp.data or []
        counts: dict[str, int] = {"unsubscribe": 0, "bounce": 0, "spam_complaint": 0, "gdpr_forget": 0}
        for r in rows:
            t = r.get("event_type", "")
            if t in counts:
                counts[t] += 1
        return counts

    def get_domain_analytics(self) -> list[dict]:
        """Sent/failed/bounce stats grouped by email domain."""
        resp = (
            self.db.table(self.tracker_table)
            .select("email,status")
            .execute()
        )
        rows = resp.data or []
        domains: dict[str, dict] = {}
        for r in rows:
            email = r.get("email", "")
            domain = email.split("@")[-1] if "@" in email else "unknown"
            if domain not in domains:
                domains[domain] = {"domain": domain, "total": 0, "sent": 0, "failed": 0, "pending": 0, "rejected": 0}
            domains[domain]["total"] += 1
            s = r.get("status", "")
            if s in domains[domain]:
                domains[domain][s.lower()] += 1

        # Add compliance bounces per domain
        comp_resp = self.db.table(self.compliance_table).select("email").eq("event_type", "bounce").execute()
        for c in comp_resp.data or []:
            email = c.get("email", "")
            domain = email.split("@")[-1] if "@" in email else "unknown"
            if domain not in domains:
                domains[domain] = {"domain": domain, "total": 0, "sent": 0, "failed": 0, "pending": 0, "rejected": 0, "bounced": 0}
            domains[domain]["bounced"] = domains[domain].get("bounced", 0) + 1

        result = sorted(domains.values(), key=lambda x: x["total"], reverse=True)
        for d in result:
            d["bounce_rate"] = round(d.get("bounced", 0) / max(d["sent"], 1), 4)
            d["reply_rate"] = round(d.get("replied", 0) / max(d["sent"], 1), 4)
        return result

    def get_hourly_distribution(self) -> list[dict]:
        """What hour of day emails are sent (UTC)."""
        resp = (
            self.db.table(self.tracker_table)
            .select("created_at")
            .eq("status", "SENT")
            .execute()
        )
        rows = resp.data or []
        hourly: dict[int, int] = defaultdict(int)
        for r in rows:
            try:
                ts = r.get("created_at", "")
                if ts:
                    hour = datetime.fromisoformat(ts).hour
                    hourly[hour] += 1
            except Exception:
                continue
        return [{"hour": h, "count": hourly[h]} for h in range(24)]

    def get_follow_up_performance(self) -> dict:
        """Stats on follow-up effectiveness."""
        resp = self.db.table(self.follow_ups_table).select("status,follow_up_number").execute()
        rows = resp.data or []
        total = len(rows)
        sent = sum(1 for r in rows if r.get("status") == "SENT")
        pending = sum(1 for r in rows if r.get("status") == "PENDING")
        skipped = sum(1 for r in rows if r.get("status") == "SKIPPED")
        failed = sum(1 for r in rows if r.get("status") == "FAILED")

        by_number: dict[int, int] = defaultdict(int)
        for r in rows:
            if r.get("status") == "SENT":
                by_number[r.get("follow_up_number", 1)] += 1

        return {
            "total": total,
            "sent": sent,
            "pending": pending,
            "skipped": skipped,
            "failed": failed,
            "sent_by_follow_up_number": dict(sorted(by_number.items())),
        }

    def get_schedule_stats(self) -> dict:
        """Schedule queue stats."""
        resp = self.db.table(self.schedule_table).select("status").execute()
        rows = resp.data or []
        return {
            "total": len(rows),
            "pending": sum(1 for r in rows if r.get("status") == "PENDING"),
            "sent": sum(1 for r in rows if r.get("status") == "SENT"),
            "cancelled": sum(1 for r in rows if r.get("status") == "CANCELLED"),
            "failed": sum(1 for r in rows if r.get("status") == "FAILED"),
        }

    def get_full_report(self, days: int = 30) -> dict:
        """Aggregate all analytics into a single report."""
        volume = self.get_volume_over_time(days)
        status_breakdown = self.get_status_breakdown()
        compliance = self.get_compliance_breakdown()
        domains = self.get_domain_analytics()
        hourly = self.get_hourly_distribution()
        follow_ups = self.get_follow_up_performance()
        schedule = self.get_schedule_stats()

        total = sum(status_breakdown.values())
        sent = status_breakdown.get("SENT", 0)
        failed = status_breakdown.get("FAILED", 0)
        pending = status_breakdown.get("PENDING", 0)

        return {
            "summary": {
                "total_emails": total,
                "total_sent": sent,
                "total_failed": failed,
                "total_pending": pending,
                "success_rate": round(sent / max(total, 1), 4),
                "failure_rate": round(failed / max(total, 1), 4),
                "total_bounces": compliance.get("bounce", 0),
                "total_unsubscribes": compliance.get("unsubscribe", 0),
                "total_spam": compliance.get("spam_complaint", 0),
            },
            "volume_over_time": volume,
            "status_breakdown": status_breakdown,
            "compliance_breakdown": compliance,
            "domain_analytics": domains[:20],  # top 20 domains
            "hourly_distribution": hourly,
            "follow_up_performance": follow_ups,
            "schedule_stats": schedule,
        }
