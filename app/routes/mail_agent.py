"""API routes for the Mailing Agent."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, PlainTextResponse
import asyncio
import json
import datetime
import uuid
import csv
import io
from collections import defaultdict

from app.deps.container import (
    get_email_generator,
    get_gmail_service,
    get_lead_ingestion,
    get_mail_tracker,
    get_langgraph_agent,
)
from app.langgraph.agent import LangGraphAgentService
from app.models.schemas import (
    ApproveEmailRequest,
    ApproveEmailResponse,
    BulkApproveRequest,
    BulkRejectRequest,
    ComplianceEvent,
    ComplianceSummary,
    DashboardSummary,
    GenerateEmailRequest,
    GenerateEmailResponse,
    LeadRecord,
    RegenerateEmailRequest,
    RejectEmailRequest,
    RejectEmailResponse,
    TemplateCreate,
    TemplateResponse,
    TemplateUpdate,
    TrackerRecord,
    UpdateDraftRequest,
    WarmupDay,
    WarmupResponse,
)
from app.services.email_generator import EmailGeneratorService
from app.services.gmail_oauth import GmailOAuthService
from app.services.ingestion import LeadIngestionService
from app.services.mail_tracker import MailTrackerService
from app.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mail-agent", tags=["mail-agent"])


# ── Leads (from the configured source table) ─────────────────────────────────


@router.get("/leads", response_model=list[LeadRecord])
def list_pending_leads(
    limit: int = 50,
    offset: int = 0,
    ingestion: LeadIngestionService = Depends(get_lead_ingestion),
):
    """Fetch pending leads from the configured Supabase source table."""
    raw = ingestion.fetch_pending_leads(limit=limit, offset=offset)
    
    if not raw:
        return []
        
    lead_ids = [row.get("id") for row in raw if row.get("id")]
    processed_ids = set()
    
    if lead_ids:
        resp = ingestion.db.table("processing_queue").select("lead_id").in_("lead_id", lead_ids).execute()
        if resp.data:
            processed_ids = {r.get("lead_id") for r in resp.data}
            
    records = []
    for row in raw:
        is_new = row.get("id") not in processed_ids
        records.append(LeadRecord(**row, is_new=is_new))
        
    return records


@router.post("/leads/ingest")
async def trigger_lead_ingestion(
    batch_id: str | None = None,
    langgraph_agent: LangGraphAgentService = Depends(get_langgraph_agent),
):
    """Manually trigger the lead discovery phase."""
    try:
        import uuid
        bid = batch_id or f"manual_ingest_{uuid.uuid4().hex[:8]}"
        leads = await langgraph_agent.discover_new_leads(bid)
        return {
            "status": "SUCCESS",
            "batch_id": bid,
            "leads_discovered": len(leads),
            "message": f"Successfully ingested {len(leads)} leads into processing queue"
        }
    except Exception as e:
        logger.error(f"Manual ingestion failed: {e}")
        raise HTTPException(500, f"Failed to ingest leads: {e}")


@router.get("/leads/{lead_id}", response_model=LeadRecord)
def get_lead(
    lead_id: str,
    ingestion: LeadIngestionService = Depends(get_lead_ingestion),
):
    row = ingestion.fetch_lead_by_id(lead_id)
    if not row:
        raise HTTPException(404, "Lead not found")
    return LeadRecord(**row)


@router.get("/leads/export/csv")
def export_leads_csv(
    ingestion: LeadIngestionService = Depends(get_lead_ingestion),
):
    """Export all leads as a CSV file for download."""
    raw = ingestion.fetch_pending_leads(limit=5000, offset=0)

    if not raw:
        output = io.StringIO()
        output.write("id,name,company,email,context\n")
        return PlainTextResponse(output.getvalue(), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=leads.csv"})

    fields = ["id", "name", "company", "email", "context", "created_at"]
    # Also grab any extra fields present in the data
    extra_fields = set()
    for row in raw:
        extra_fields.update(k for k in row if k not in fields and not k.startswith("_"))
    fields.extend(sorted(extra_fields))

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in raw:
        writer.writerow(row)

    return PlainTextResponse(output.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=leads.csv"})


# ── Email generation ─────────────────────────────────────────────────────────


@router.post("/generate", response_model=GenerateEmailResponse)
def generate_email(
    req: GenerateEmailRequest,
    ingestion: LeadIngestionService = Depends(get_lead_ingestion),
    email_gen: EmailGeneratorService = Depends(get_email_generator),
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """
    1. Fetch lead from source table
    2. Generate personalised email via LLM
    3. Create a Gmail draft
    4. Create tracker record with PENDING status
    """
    lead = ingestion.fetch_lead_by_id(req.lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")

    company_name = lead.get("name") or lead.get("company") or "Unknown"
    context = lead.get("context") or lead.get("Context") or ""
    recipient_email = lead.get("email") or lead.get("Email") or ""

    if not recipient_email:
        raise HTTPException(400, "Lead has no email address")

    # Generate email content
    email_content = email_gen.generate(company_name, context, recipient_email)

    # Create tracker record
    record = tracker.create_record(
        company_name=company_name,
        email=recipient_email,
        subject=email_content["subject"],
        body_preview=email_content["body_text"],
        status="PENDING",
    )

    ingestion.mark_processing(req.lead_id)

    return GenerateEmailResponse(
        tracker_id=record["id"],
        company_name=company_name,
        email=recipient_email,
        subject=email_content["subject"],
        body_text=email_content["body_text"],
        status="PENDING",
    )


@router.get("/tracker/{tracker_id}/context")
def get_tracker_lead_context(
    tracker_id: str,
    tracker: MailTrackerService = Depends(get_mail_tracker),
    ingestion: LeadIngestionService = Depends(get_lead_ingestion),
):
    record = tracker.get_record(tracker_id)
    if not record:
        raise HTTPException(404, "Tracker record not found")
    
    lead = ingestion.fetch_lead_by_email(record["email"])
    if not lead:
        # Fallback to name search if email fails (less reliable)
        leads = ingestion.fetch_pending_leads() # This is bad, but let's see
        lead = next((l for l in leads if l["name"] == record["company_name"]), None)
        
    if not lead:
        raise HTTPException(404, "Original lead context not found")
    
    return LeadRecord(**lead)


# ── Approval & send flow ─────────────────────────────────────────────────────


@router.post("/approve", response_model=ApproveEmailResponse)
def approve_and_send(
    req: ApproveEmailRequest,
    gmail_service: GmailOAuthService = Depends(get_gmail_service),
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """
    Approve a pending email and send it via Gmail.
    Updates tracker to SENT on success, FAILED on error.
    """
    record = tracker.get_record(req.tracker_id)
    if not record:
        raise HTTPException(404, "Tracker record not found")
    if record["status"] != "PENDING":
        raise HTTPException(400, f"Email is already {record['status']}")

    recipient = record["email"]
    subject = record["email_subject"]
    body_text = record["email_body_preview"]

    try:
        msg_id, thread_id = gmail_service.safe_send_email(
            recipient=recipient,
            subject=subject,
            body_text=body_text,
        )
        tracker.update_status(
            req.tracker_id,
            "SENT",
            gmail_message_id=msg_id,
            thread_id=thread_id,
        )
        return ApproveEmailResponse(
            tracker_id=req.tracker_id,
            status="SENT",
            gmail_message_id=msg_id,
        )
    except Exception as e:
        logger.error("Failed to send email: %s", e)
        tracker.update_status(req.tracker_id, "FAILED", error=str(e))
        raise HTTPException(500, f"Failed to send email: {e}")


@router.post("/reject", response_model=RejectEmailResponse)
def reject_email(
    req: RejectEmailRequest,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Reject a pending email (won't be sent)."""
    record = tracker.get_record(req.tracker_id)
    if not record:
        raise HTTPException(404, "Tracker record not found")
    if record["status"] != "PENDING":
        raise HTTPException(400, f"Email is already {record['status']}")

    tracker.update_status(req.tracker_id, "REJECTED", error=req.reason)
    return RejectEmailResponse(tracker_id=req.tracker_id, status="REJECTED")


@router.post("/regenerate", response_model=GenerateEmailResponse)
def regenerate_email(
    req: RegenerateEmailRequest,
    ingestion: LeadIngestionService = Depends(get_lead_ingestion),
    email_gen: EmailGeneratorService = Depends(get_email_generator),
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """
    Regenerate an email draft based on user feedback.
    """
    # 1. Fetch existing tracker record
    record = tracker.get_record(req.tracker_id)
    if not record:
        raise HTTPException(404, "Tracker record not found")
    
    # 2. Find associated lead (we'd need lead_id in tracker, or find by email/company)
    # For now, let's assume we can fetch context from the tracker or leads table
    # mail_agent_tracker doesn't have lead_id currently, but we can search leads by email
    leads = ingestion.db.table(ingestion.table).select("*").eq("email", record["email"]).execute()
    if not leads.data:
         # Fallback: Use what we have in tracker
         company_name = record["company_name"]
         context = "Previous context not found in source table."
    else:
        lead = leads.data[0]
        company_name = lead.get("name") or lead.get("company") or record["company_name"]
        context = lead.get("context") or lead.get("Context") or ""

    # 3. Regenerate
    email_content = email_gen.regenerate(
        company_name=company_name,
        context=context,
        recipient_email=record["email"],
        feedback=req.feedback,
        prev_subject=record["email_subject"],
        prev_body=record["email_body_preview"]
    )

    # 4. Update tracker record
    tracker.update_record(
        req.tracker_id,
        email_subject=email_content["subject"],
        email_body_preview=email_content["body_text"],
        status="PENDING" # Reset status if it was failed/rejected
    )

    return GenerateEmailResponse(
        tracker_id=req.tracker_id,
        company_name=company_name,
        email=record["email"],
        subject=email_content["subject"],
        body_text=email_content["body_text"],
        status="PENDING",
    )


@router.post("/bulk-approve")
def bulk_approve_emails(
    req: BulkApproveRequest,
    gmail_service: GmailOAuthService = Depends(get_gmail_service),
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Approve and send multiple emails at once."""
    results = []
    for tid in req.tracker_ids:
        try:
            record = tracker.get_record(tid)
            if not record or record["status"] != "PENDING":
                results.append({"tracker_id": tid, "status": "SKIPPED", "error": "Not found or not pending"})
                continue
                
            msg_id = gmail_service.safe_send_email(
                recipient=record["email"],
                subject=record["email_subject"],
                body_text=record["email_body_preview"],
            )
            tracker.update_status(tid, "SENT", gmail_message_id=msg_id)
            results.append({"tracker_id": tid, "status": "SENT", "gmail_message_id": msg_id})
        except Exception as e:
            logger.error(f"Bulk approve failed for {tid}: {e}")
            tracker.update_status(tid, "FAILED", error=str(e))
            results.append({"tracker_id": tid, "status": "FAILED", "error": str(e)})
            
    return {"results": results, "total": len(req.tracker_ids)}


# ── Tracker records ──────────────────────────────────────────────────────────


@router.get("/tracker", response_model=list[TrackerRecord])
def list_tracker_records(
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """List all mail agent tracker records, optionally filtered by status."""
    raw = tracker.list_records(status=status, limit=limit, offset=offset)
    return [TrackerRecord(**r) for r in raw]


@router.get("/tracker/{tracker_id}", response_model=TrackerRecord)
def get_tracker_record(
    tracker_id: str,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    record = tracker.get_record(tracker_id)
    if not record:
        raise HTTPException(404, "Tracker record not found")
    return TrackerRecord(**record)


@router.patch("/tracker/{tracker_id}")
def update_draft(
    tracker_id: str,
    req: UpdateDraftRequest,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Update the subject or body of a drafted email before sending."""
    record = tracker.get_record(tracker_id)
    if not record:
        raise HTTPException(404, "Tracker record not found")
    if record["status"] not in ["PENDING", "REJECTED", "FAILED"]:
        raise HTTPException(400, f"Cannot edit an email with status {record['status']}")

    updates = {}
    if req.subject is not None:
        updates["email_subject"] = req.subject
    if req.body_text is not None:
        updates["email_body_preview"] = req.body_text

    if not updates:
        return {"message": "No updates provided", "tracker_id": tracker_id}

    updated_record = tracker.update_record(tracker_id, **updates)
    return {"message": "Draft updated successfully", "tracker_id": tracker_id}



# ── Dashboard ────────────────────────────────────────────────────────────────


@router.get("/dashboard/summary", response_model=DashboardSummary)
def get_dashboard_summary(
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    counts = tracker.get_summary()
    return DashboardSummary(
        total=counts.get("total", 0),
        pending=counts.get("PENDING", 0),
        approved=counts.get("APPROVED", 0),
        sent=counts.get("SENT", 0),
        rejected=counts.get("REJECTED", 0),
        failed=counts.get("FAILED", 0),
    )
@router.get("/config/public")
async def get_public_config(
    settings: Settings = Depends(get_settings)
):
    """Expose public configuration (URL and Anon Key) to the frontend."""
    return {
        "supabase_url": settings.supabase_url,
        "supabase_anon_key": settings.supabase_anon_key,
        "leads_table": settings.supabase_leads_table,
        "tracker_table": settings.supabase_mail_agent_table
    }


@router.get("/live-updates")
async def live_updates(
    ingestion: LeadIngestionService = Depends(get_lead_ingestion),
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """
    SSE endpoint for live dashboard updates.
    Monitors tracker and lead tables for changes and notifies the frontend.
    """
    async def event_generator():
        last_tracker_count = 0
        last_leads_count = 0
        last_queue_status = ""
        
        while True:
            try:
                # Check for changes in tracker table
                tracker_res = tracker.db.table(tracker.table).select("count", count="exact").execute()
                current_tracker_count = tracker_res.count if tracker_res.count is not None else 0
                
                # Check for changes in leads table
                leads_res = ingestion.db.table(ingestion.table).select("count", count="exact").execute()
                current_leads_count = leads_res.count if leads_res.count is not None else 0
                
                # Check for active processing in queue
                queue_res = tracker.db.table("processing_queue").select("status").in_("status", ["PROCESSING", "PENDING"]).execute()
                current_queue_status = str(len(queue_res.data)) if queue_res.data else "0"
                
                # If anything changed, notify the frontend
                if (current_tracker_count != last_tracker_count or 
                    current_leads_count != last_leads_count or 
                    current_queue_status != last_queue_status):
                    
                    last_tracker_count = current_tracker_count
                    last_leads_count = current_leads_count
                    last_queue_status = current_queue_status
                    yield f"data: {json.dumps({'type': 'update', 'timestamp': datetime.datetime.now().isoformat()})}\n\n"
                
            except Exception as e:
                logger.error(f"SSE Error: {e}")
                
            await asyncio.sleep(2)  # Check every 2 seconds

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Templates CRUD ─────────────────────────────────────────────────────────


@router.get("/templates", response_model=list[TemplateResponse])
def list_templates(
    search: str | None = None,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """List all email templates, optionally filtered by search."""
    q = tracker.db.table("mail_agent_templates").select("*").order("updated_at", desc=True)
    if search:
        q = q.ilike("name", f"%{search}%")
    resp = q.execute()
    return resp.data or []


@router.get("/templates/{template_id}", response_model=TemplateResponse)
def get_template(
    template_id: str,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    resp = tracker.db.table("mail_agent_templates").select("*").eq("id", template_id).limit(1).execute()
    rows = resp.data or []
    if not rows:
        raise HTTPException(404, "Template not found")
    return rows[0]


@router.post("/templates", response_model=TemplateResponse)
def create_template(
    req: TemplateCreate,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    record = {
        "id": str(uuid.uuid4()),
        "name": req.name,
        "subject": req.subject,
        "body": req.body,
        "created_at": now,
        "updated_at": now,
    }
    tracker.db.table("mail_agent_templates").insert(record).execute()
    return record


@router.patch("/templates/{template_id}", response_model=TemplateResponse)
def update_template(
    template_id: str,
    req: TemplateUpdate,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    existing = tracker.db.table("mail_agent_templates").select("*").eq("id", template_id).limit(1).execute()
    if not existing.data:
        raise HTTPException(404, "Template not found")

    payload = {"updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    if req.name is not None:
        payload["name"] = req.name
    if req.subject is not None:
        payload["subject"] = req.subject
    if req.body is not None:
        payload["body"] = req.body

    tracker.db.table("mail_agent_templates").update(payload).eq("id", template_id).execute()
    updated = tracker.db.table("mail_agent_templates").select("*").eq("id", template_id).limit(1).execute()
    return updated.data[0]


@router.delete("/templates/{template_id}")
def delete_template(
    template_id: str,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    tracker.db.table("mail_agent_templates").delete().eq("id", template_id).execute()
    return {"message": "Template deleted"}


# ── Bulk Reject ─────────────────────────────────────────────────────────────


@router.post("/bulk-reject")
def bulk_reject_emails(
    req: BulkRejectRequest,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Reject multiple pending emails at once."""
    results = []
    for tid in req.tracker_ids:
        try:
            record = tracker.get_record(tid)
            if not record or record["status"] != "PENDING":
                results.append({"tracker_id": tid, "status": "SKIPPED", "error": "Not found or not pending"})
                continue
            tracker.update_status(tid, "REJECTED", error=req.reason)
            results.append({"tracker_id": tid, "status": "REJECTED"})
        except Exception as e:
            logger.error(f"Bulk reject failed for {tid}: {e}")
            results.append({"tracker_id": tid, "status": "FAILED", "error": str(e)})
    return {"results": results, "total": len(req.tracker_ids)}


# ── Compliance Tracker ──────────────────────────────────────────────────────


@router.get("/compliance/summary", response_model=ComplianceSummary)
def get_compliance_summary(
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    resp = tracker.db.table("mail_agent_compliance").select("event_type").execute()
    rows = resp.data or []
    counts = {"total": len(rows), "unsubscribe": 0, "bounce": 0, "spam": 0, "gdpr_delete": 0}
    for r in rows:
        t = r.get("event_type", "")
        if t in counts:
            counts[t] += 1
    return ComplianceSummary(
        total=counts["total"],
        unsubscribes=counts["unsubscribe"],
        bounces=counts["bounce"],
        spam=counts["spam"],
        gdpr=counts["gdpr_delete"],
    )


@router.get("/compliance/list", response_model=list[ComplianceEvent])
def list_compliance_events(
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    q = tracker.db.table("mail_agent_compliance").select("*").order("created_at", desc=True).limit(limit).range(offset, offset + limit - 1)
    if search:
        q = q.or_(f"email.ilike.%{search}%,name.ilike.%{search}%")
    resp = q.execute()
    return resp.data or []


# ── Warmup Dashboard ────────────────────────────────────────────────────────


@router.get("/warmup", response_model=WarmupResponse)
def get_warmup_data(
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Compute warmup stats from sent emails in the tracker."""
    now = datetime.datetime.now(datetime.timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    # Today's sent emails
    today_resp = (
        tracker.db.table(tracker.table)
        .select("*")
        .eq("status", "SENT")
        .gte("created_at", today_start)
        .execute()
    )
    today_rows = today_resp.data or []

    # Count today's total sent and failed
    sent_today = len(today_rows)
    failed_resp = (
        tracker.db.table(tracker.table)
        .select("*")
        .eq("status", "FAILED")
        .gte("created_at", today_start)
        .execute()
    )
    bounced_today = len(failed_resp.data or [])

    # Last 14 days of sent emails
    fourteen_days_ago = (now - datetime.timedelta(days=14)).isoformat()
    history_resp = (
        tracker.db.table(tracker.table)
        .select("created_at,status")
        .gte("created_at", fourteen_days_ago)
        .execute()
    )
    history_rows = history_resp.data or []

    # Group by day
    daily = defaultdict(lambda: {"sent": 0, "failed": 0})
    for r in history_rows:
        day = r.get("created_at", "")[:10]
        if r.get("status") == "SENT":
            daily[day]["sent"] += 1
        elif r.get("status") == "FAILED":
            daily[day]["failed"] += 1

    # Build 14-day history
    history = []
    for i in range(13, -1, -1):
        d = (now - datetime.timedelta(days=i)).strftime("%m/%d")
        date_key = (now - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        sent = daily[date_key]["sent"] if date_key in daily else 0
        failed = daily[date_key]["failed"] if date_key in daily else 0
        history.append(WarmupDay(
            label=d,
            sent=sent,
            bounced=failed,
            bounce_rate=round(failed / max(sent, 1), 4),
        ))

    # Determine reputation
    recent_failures = sum(1 for r in history_rows if r.get("status") == "FAILED")
    total_recent = len(history_rows)
    fail_rate = recent_failures / max(total_recent, 1)
    reputation = "warning" if fail_rate > 0.1 else "healthy"
    if fail_rate > 0.25:
        reputation = "poor"

    # Recommended daily limit (ramp up gradually)
    max_daily = max((h.sent for h in history), default=0)
    recommended = min(max(max_daily + 10, 50), 200)

    return WarmupResponse(
        today={"sent": sent_today, "bounced": bounced_today, "label": "Today", "bounce_rate": 0},
        history=history,
        reputation=reputation,
        recommended_daily=recommended,
    )


@router.post("/check-replies")
def check_replies(
    gmail_service: GmailOAuthService = Depends(get_gmail_service),
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Scan Gmail inbox for replies to our sent emails and store them."""
    try:
        potential = gmail_service.check_for_replies()
    except Exception as e:
        logger.error("Gmail scan failed: %s", e)
        raise HTTPException(500, f"Gmail scan failed: {e}")

    new_replies = []
    for reply in potential:
        tid = reply["thread_id"]
        gid = reply["gmail_message_id"]

        # Skip if we already stored this message
        if tracker.find_by_gmail_message_id(gid):
            continue

        # Find our sent email in this thread
        sent_records = tracker.find_sent_by_thread(tid)
        if not sent_records:
            continue

        original = sent_records[0]
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        reply_record = tracker.create_record(
            company_name=original.get("company_name", ""),
            email=original.get("email", ""),
            subject=f"Re: {reply['subject']}" if reply["subject"] else "Reply",
            body_preview="",
            context="",
            status="REPLY",
            thread_id=tid,
            gmail_message_id=gid,
            is_reply=True,
        )
        new_replies.append(reply_record)

    return {"detected": len(new_replies), "replies": new_replies}