"""API routes for Deep Research Agent."""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File
from supabase import Client

from app.config.database import get_supabase
from app.services.deep_research.engine import leads_from_csv, research_batch, research_single_lead
from app.services.deep_research.schemas import (
    BatchProgress,
    LeadInput,
    PipelineConfig,
    ResearchBrief,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["deep-research"])

# In-memory state for running batches
_running_batches: dict[str, BatchProgress] = {}


# ── CSV Upload & Batch Pipeline ─────────────────────────────────────────────────

@router.post("/upload-csv")
async def upload_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Client = Depends(get_supabase),
) -> dict:
    """Upload a CSV file and start the research pipeline.

    CSV columns expected: name, sector, size (or Name, Sector, Size)
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only CSV files accepted")

    import tempfile
    content = await file.read()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    leads = leads_from_csv(tmp_path)

    import os
    os.unlink(tmp_path)

    if not leads:
        raise HTTPException(400, "No valid leads found in CSV. Expected columns: name, sector, size")

    # Insert leads into Supabase
    lead_map = {}
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for lead in leads:
        try:
            resp = db.table("leads").insert({
                "name": lead.name,
                "sector": lead.sector,
                "size": lead.size,
                "context": "",
                "email": "",
                "created_at": now,
            }).execute()
            if resp.data:
                lead_map[lead.name] = resp.data[0].get("id", "")
        except Exception:
            pass

    # Start in background
    progress = BatchProgress(
        batch_id=f"csv_{file.filename.rsplit('.',1)[0]}",
        pipeline_name="standard_b2b",
        total_leads=len(leads),
    )
    _running_batches[progress.batch_id] = progress

    background_tasks.add_task(_run_batch_background, leads, progress, db, lead_map)

    return {
        "batch_id": progress.batch_id,
        "total_leads": len(leads),
        "message": f"Research pipeline started for {len(leads)} leads",
    }


async def _run_batch_background(
    leads: list[LeadInput],
    progress: BatchProgress,
    db: Client,
    lead_map: dict[str, str] | None = None,
) -> None:
    """Run the batch and update progress."""
    try:
        result = await research_batch(leads, db=db, lead_map=lead_map)
        progress.processed = result.processed
        progress.contacts_found = result.contacts_found
        progress.briefs_generated = result.briefs_generated
        progress.errors = result.errors
        progress.skipped = result.skipped
        progress.status = "COMPLETED"
        progress.lead_results = result.lead_results
    except Exception as e:
        logger.error(f"Batch {progress.batch_id} failed: {e}")
        progress.status = "FAILED"


# ── Single Lead Research ───────────────────────────────────────────────────────

@router.post("/single")
async def research_single(
    data: dict[str, Any],
    db: Client = Depends(get_supabase),
) -> dict:
    """Research a single lead."""
    lead = LeadInput(
        name=data.get("name", ""),
        sector=data.get("sector", ""),
        size=data.get("size", ""),
    )
    if not lead.name:
        raise HTTPException(400, "name is required")

    lead_id = data.get("lead_id", "")
    brief = await research_single_lead(lead, db=db, lead_id=lead_id)
    return brief.model_dump()


# ── Batch Progress ──────────────────────────────────────────────────────────────

@router.get("/batch/{batch_id}")
async def get_batch_progress(batch_id: str) -> dict:
    """Get current progress of a running batch."""
    progress = _running_batches.get(batch_id)
    if not progress:
        raise HTTPException(404, "Batch not found")
    return progress.model_dump()


@router.get("/batches")
async def list_batches() -> list[dict]:
    """List all batches."""
    return [
        {"batch_id": bid, "status": p.status, "total": p.total_leads, "processed": p.processed}
        for bid, p in _running_batches.items()
    ]


# ── Pipeline Config ─────────────────────────────────────────────────────────────

@router.get("/config")
async def get_pipeline_config() -> dict:
    """Get the default pipeline configuration."""
    return PipelineConfig(name="standard_b2b").model_dump()


# ── Research Briefs (from Supabase) ──────────────────────────────────────────────

@router.get("/brief/{lead_id}")
async def get_research_brief(
    lead_id: str,
    db: Client = Depends(get_supabase),
) -> dict:
    """Get the latest research brief for a lead."""
    try:
        resp = (
            db.table("research_briefs")
            .select("*")
            .eq("lead_id", lead_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]
        raise HTTPException(404, "No research brief found for this lead")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get research brief: {e}")
        raise HTTPException(500, str(e))


@router.get("/briefs")
async def list_research_briefs(
    confidence_min: float = 0.0,
    limit: int = 50,
    db: Client = Depends(get_supabase),
) -> list[dict]:
    """List recent research briefs, optionally filtered by min confidence."""
    try:
        q = db.table("research_briefs").select("*").order("created_at", desc=True).limit(limit)
        if confidence_min > 0:
            q = q.gte("confidence", confidence_min)
        resp = q.execute()
        return resp.data or []
    except Exception as e:
        logger.error(f"Failed to list research briefs: {e}")
        return []


@router.get("/brief/by-email/{email}")
async def get_research_brief_by_email(
    email: str,
    db: Client = Depends(get_supabase),
) -> dict:
    """Get the latest research brief for a lead by email."""
    try:
        resp = (
            db.table("research_briefs")
            .select("*")
            .eq("lead_email", email)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]
        raise HTTPException(404, "No research brief found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get research brief: {e}")
        raise HTTPException(500, str(e))


# ── Health ──────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "running_batches": len(_running_batches)}
