"""API routes for Email Analytics & Insights Dashboard."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from app.services.analytics import AnalyticsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/report")
def get_analytics_report(
    days: int = Query(30, ge=1, le=365, description="Number of days of history to include"),
):
    """Get the full analytics report with volume, domains, hourly distribution, and more."""
    svc = AnalyticsService()
    return svc.get_full_report(days=days)


@router.get("/volume")
def get_volume(
    days: int = Query(30, ge=1, le=365),
):
    """Get daily send/fail volume over time."""
    svc = AnalyticsService()
    return svc.get_volume_over_time(days=days)


@router.get("/status-breakdown")
def get_status_breakdown():
    """Get total counts per email status."""
    svc = AnalyticsService()
    return svc.get_status_breakdown()


@router.get("/domains")
def get_domain_analytics():
    """Get sent/failed/bounce stats grouped by email domain."""
    svc = AnalyticsService()
    return svc.get_domain_analytics()


@router.get("/hourly")
def get_hourly_distribution():
    """Get hourly send distribution."""
    svc = AnalyticsService()
    return svc.get_hourly_distribution()


@router.get("/compliance-breakdown")
def get_compliance_breakdown():
    """Get compliance event counts by type."""
    svc = AnalyticsService()
    return svc.get_compliance_breakdown()


@router.get("/follow-ups")
def get_follow_up_performance():
    """Get follow-up effectiveness stats."""
    svc = AnalyticsService()
    return svc.get_follow_up_performance()


@router.get("/schedules")
def get_schedule_stats():
    """Get schedule queue stats."""
    svc = AnalyticsService()
    return svc.get_schedule_stats()
