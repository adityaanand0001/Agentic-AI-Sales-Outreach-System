"""Research cache — avoid re-researching the same company within TTL."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from app.services.deep_research.schemas import ResearchBrief

CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent / ".research_cache"
CACHE_DIR.mkdir(exist_ok=True)

COMPANY_TTL_DAYS = 7
SECTOR_TTL_DAYS = 7


def cache_key(company_name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in company_name.lower().strip())


def get_cached_brief(company_name: str) -> ResearchBrief | None:
    """Return cached brief if still fresh."""
    key = cache_key(company_name)
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text())
        cached_date = datetime.fromisoformat(data.get("research_date", "2000-01-01"))
        age = (datetime.now(timezone.utc) - cached_date).days
        if age <= COMPANY_TTL_DAYS:
            return ResearchBrief(**data)
    except Exception:
        pass

    # Expired — delete
    path.unlink(missing_ok=True)
    return None


def set_cached_brief(brief: ResearchBrief) -> None:
    """Store brief in cache."""
    key = cache_key(brief.lead_name)
    path = CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps(brief.model_dump(), indent=2))


def get_cached_sector_research(sector: str) -> dict | None:
    """Return cached sector trends if still fresh."""
    key = "sector_" + cache_key(sector)
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text())
        cached_date = datetime.fromisoformat(data.get("cached_at", "2000-01-01"))
        if (datetime.now(timezone.utc) - cached_date).days <= SECTOR_TTL_DAYS:
            return data.get("data", {})
    except Exception:
        pass

    path.unlink(missing_ok=True)
    return None


def set_cached_sector_research(sector: str, data: dict) -> None:
    """Store sector research in cache."""
    key = "sector_" + cache_key(sector)
    path = CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps({
        "cached_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }, indent=2))
