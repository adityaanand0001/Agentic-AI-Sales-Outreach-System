"""API routes for LangGraph-powered autonomous agent."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.deps.container import get_langgraph_agent
from app.langgraph.agent import LangGraphAgentService
from app.langgraph.visualization import WorkflowVisualizer
from app.models.schemas import LogEntryResponse, BatchSummaryResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/langgraph-agent", tags=["langgraph-agent"])


# ── Request/Response Models ──────────────────────────────────────────────────

class LeadProcessRequest(BaseModel):
    lead_id: str = Field(..., description="ID of the lead to process")
    batch_id: str | None = Field(None, description="Optional batch ID")


class BatchProcessRequest(BaseModel):
    lead_ids: List[str] = Field(..., description="List of lead IDs to process")
    batch_id: str | None = Field(None, description="Optional batch ID")


class WorkflowStatusResponse(BaseModel):
    workflow_status: str
    queue_status: Dict[str, int]
    ai_decisions: Dict[str, int]
    avg_ai_confidence: float
    total_ai_decisions: int
    workflow_version: str
    last_updated: str
    error: str | None = None


class VisualizationResponse(BaseModel):
    mermaid_diagram: str
    message: str


class ExecutionReportResponse(BaseModel):
    report_generated: str
    summary: Dict[str, Any]
    stage_analysis: Dict[str, Any]
    action_analysis: Dict[str, Any]
    ai_analysis: Dict[str, Any]
    performance_metrics: Dict[str, Any]
    error: str | None = None


# ── Agent Control ────────────────────────────────────────────────────────────

@router.post("/process-lead")
async def process_single_lead(
    request: LeadProcessRequest,
    agent: LangGraphAgentService = Depends(get_langgraph_agent),
) -> Dict[str, Any]:
    """Process a single lead through the LangGraph workflow."""
    try:
        result = await agent.process_single_lead(request.lead_id, request.batch_id)
        return result
    except Exception as e:
        logger.error(f"Failed to process lead {request.lead_id}: {e}")
        raise HTTPException(500, f"Failed to process lead: {e}")


@router.post("/process-batch")
async def process_batch(
    request: BatchProcessRequest,
    agent: LangGraphAgentService = Depends(get_langgraph_agent),
) -> Dict[str, Any]:
    """Process a batch of leads through the LangGraph workflow."""
    try:
        result = await agent.process_batch(request.lead_ids, request.batch_id)
        return result
    except Exception as e:
        logger.error(f"Failed to process batch: {e}")
        raise HTTPException(500, f"Failed to process batch: {e}")


@router.post("/run-autonomous-batch")
async def run_autonomous_batch(
    batch_id: str | None = Query(None, description="Optional batch ID"),
    agent: LangGraphAgentService = Depends(get_langgraph_agent),
) -> Dict[str, Any]:
    """Run a full autonomous batch processing cycle."""
    try:
        result = await agent.run_autonomous_batch(batch_id)
        return result
    except Exception as e:
        logger.error(f"Failed to run autonomous batch: {e}")
        raise HTTPException(500, f"Failed to run autonomous batch: {e}")


@router.post("/run-autonomous-batch/stream")
async def run_autonomous_batch_stream(
    agent: LangGraphAgentService = Depends(get_langgraph_agent),
):
    """Run batch with real-time SSE event stream."""
    queue = asyncio.Queue()

    async def run_batch():
        await agent.run_autonomous_batch_with_events(queue)

    async def event_generator():
        task = asyncio.create_task(run_batch())
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("DONE", "ERROR"):
                    break
        except asyncio.CancelledError:
            task.cancel()
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Workflow Status & Monitoring ─────────────────────────────────────────────

@router.get("/status", response_model=WorkflowStatusResponse)
async def get_workflow_status(
    agent: LangGraphAgentService = Depends(get_langgraph_agent),
):
    """Get current status of the LangGraph workflow."""
    try:
        status = await agent.get_workflow_status()
        return WorkflowStatusResponse(**status)
    except Exception as e:
        logger.error(f"Failed to get workflow status: {e}")
        raise HTTPException(500, f"Failed to get workflow status: {e}")


@router.get("/logs", response_model=List[LogEntryResponse])
async def get_execution_logs(
    tracker_id: str | None = Query(None),
    batch_id: str | None = Query(None),
    limit: int = Query(50),
    agent: LangGraphAgentService = Depends(get_langgraph_agent),
):
    """Fetch AI decision logs."""
    logs = await agent.get_execution_logs(tracker_id=tracker_id, batch_id=batch_id, limit=limit)
    return logs


@router.get("/batches", response_model=List[BatchSummaryResponse])
async def get_batch_history(
    limit: int = Query(20),
    agent: LangGraphAgentService = Depends(get_langgraph_agent),
):
    """Fetch historical batch summaries."""
    batches = await agent.get_batch_history(limit=limit)
    return batches


@router.get("/visualize/mermaid")
async def get_workflow_mermaid(
    agent: LangGraphAgentService = Depends(get_langgraph_agent),
) -> VisualizationResponse:
    """Get Mermaid.js diagram of the workflow."""
    try:
        diagram = agent.visualize_workflow()
        return VisualizationResponse(
            mermaid_diagram=diagram,
            message="Mermaid.js diagram generated successfully",
        )
    except Exception as e:
        logger.error(f"Failed to generate workflow diagram: {e}")
        raise HTTPException(500, f"Failed to generate workflow diagram: {e}")


@router.get("/visualize/plot")
async def generate_workflow_plot(
    output_path: str | None = Query(None, description="Optional output file path"),
    agent: LangGraphAgentService = Depends(get_langgraph_agent),
):
    """Generate and save workflow plot."""
    try:
        # Create visualizer
        from app.langgraph.workflow import build_mailing_workflow
        from app.deps.container import (
            get_supabase,
            get_lead_ingestion,
            get_email_generator,
            get_mail_tracker,
            get_gmail_service,
        )

        # Get dependencies
        db = get_supabase()
        ingestion = get_lead_ingestion(db)
        email_gen = get_email_generator()
        tracker = get_mail_tracker(db)
        gmail = get_gmail_service()

        # Build workflow and create visualizer
        workflow = build_mailing_workflow(db, ingestion, email_gen, tracker, gmail)
        visualizer = WorkflowVisualizer(workflow)

        # Generate plot
        visualizer.plot_workflow(output_path)

        return {
            "status": "success",
            "message": f"Workflow plot generated{' and saved' if output_path else ''}",
            "output_path": output_path,
        }
    except Exception as e:
        logger.error(f"Failed to generate workflow plot: {e}")
        raise HTTPException(500, f"Failed to generate workflow plot: {e}")


# ── Execution Analysis ───────────────────────────────────────────────────────

@router.get("/execution-report")
async def get_execution_report(
    limit: int = Query(100, description="Number of recent executions to analyze"),
    agent: LangGraphAgentService = Depends(get_langgraph_agent),
) -> ExecutionReportResponse:
    """Generate execution report from recent workflow runs."""
    try:
        # Fetch recent execution data from database
        # This is a simplified version - in production, you'd query actual execution logs
        from datetime import datetime, timedelta, timezone

        # Get recent processing queue entries
        resp = agent.db.table("processing_queue").select("*").order("created_at", desc=True).limit(limit).execute()
        queue_entries = resp.data or []

        # Transform to execution data format
        execution_data = []
        for entry in queue_entries:
            execution_data.append({
                "lead_id": entry.get("lead_id"),
                "batch_id": entry.get("batch_id"),
                "status": entry.get("status"),
                "result": {
                    "processing_stage": entry.get("processing_stage"),
                    "ai_confidence": entry.get("ai_confidence"),
                    "processing_time": 0,  # Would calculate from timestamps
                }
            })

        # Create visualizer and generate report
        from app.langgraph.workflow import build_mailing_workflow
        from app.deps.container import (
            get_supabase,
            get_lead_ingestion,
            get_email_generator,
            get_mail_tracker,
            get_gmail_service,
        )

        # Get dependencies
        db = get_supabase()
        ingestion = get_lead_ingestion(db)
        email_gen = get_email_generator()
        tracker = get_mail_tracker(db)
        gmail = get_gmail_service()

        # Build workflow and create visualizer
        workflow = build_mailing_workflow(db, ingestion, email_gen, tracker, gmail)
        visualizer = WorkflowVisualizer(workflow)

        report = visualizer.generate_execution_report(execution_data)

        if "error" in report:
            raise HTTPException(500, report["error"])

        return ExecutionReportResponse(**report)

    except Exception as e:
        logger.error(f"Failed to generate execution report: {e}")
        raise HTTPException(500, f"Failed to generate execution report: {e}")


@router.get("/performance-metrics/plot")
async def plot_performance_metrics(
    limit: int = Query(100, description="Number of recent executions to analyze"),
    output_path: str | None = Query(None, description="Optional output file path"),
    agent: LangGraphAgentService = Depends(get_langgraph_agent),
):
    """Plot performance metrics from recent workflow executions."""
    try:
        # Fetch recent execution data
        resp = agent.db.table("processing_queue").select("*").order("created_at", desc=True).limit(limit).execute()
        queue_entries = resp.data or []

        # Transform to execution data format
        execution_data = []
        for entry in queue_entries:
            execution_data.append({
                "lead_id": entry.get("lead_id"),
                "batch_id": entry.get("batch_id"),
                "status": entry.get("status"),
                "result": {
                    "processing_stage": entry.get("processing_stage"),
                    "ai_confidence": entry.get("ai_confidence"),
                    "processing_time": 0,
                }
            })

        # Create visualizer and plot metrics
        from app.langgraph.workflow import build_mailing_workflow
        from app.deps.container import (
            get_supabase,
            get_lead_ingestion,
            get_email_generator,
            get_mail_tracker,
            get_gmail_service,
        )

        # Get dependencies
        db = get_supabase()
        ingestion = get_lead_ingestion(db)
        email_gen = get_email_generator()
        tracker = get_mail_tracker(db)
        gmail = get_gmail_service()

        # Build workflow and create visualizer
        workflow = build_mailing_workflow(db, ingestion, email_gen, tracker, gmail)
        visualizer = WorkflowVisualizer(workflow)

        visualizer.plot_performance_metrics(execution_data, output_path)

        return {
            "status": "success",
            "message": f"Performance metrics plot generated{' and saved' if output_path else ''}",
            "output_path": output_path,
            "executions_analyzed": len(execution_data),
        }

    except Exception as e:
        logger.error(f"Failed to plot performance metrics: {e}")
        raise HTTPException(500, f"Failed to plot performance metrics: {e}")


# ── Workflow Configuration ───────────────────────────────────────────────────

@router.get("/config")
async def get_workflow_config(
    agent: LangGraphAgentService = Depends(get_langgraph_agent),
):
    """Get current workflow configuration."""
    try:
        return {
            "workflow_version": "1.0.0",
            "auto_send_threshold": agent.auto_send_threshold,
            "batch_size": agent.batch_size,
            "processing_delay": agent.processing_delay,
            "max_retries": agent.max_retries,
            "description": "LangGraph-powered autonomous mailing agent workflow",
            "nodes": [
                "discover",
                "prioritize",
                "generate",
                "quality_check",
                "decision",
                "complete",
            ],
            "conditional_edges": [],
        }
    except Exception as e:
        logger.error(f"Failed to get workflow config: {e}")
        raise HTTPException(500, f"Failed to get workflow config: {e}")