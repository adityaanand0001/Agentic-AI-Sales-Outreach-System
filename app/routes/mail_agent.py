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
    CampaignCreate,
    CampaignUpdate,
    CampaignAssignRequest,
    ComplianceEvent,
    ComplianceSummary,
    DashboardSummary,
    GenerateEmailRequest,
    GenerateEmailResponse,
    LeadNoteCreate,
    LeadRecord,
    LeadScoreRequest,
    LeadScoreResponse,
    LeadScore,
    RegenerateEmailRequest,
    RejectEmailRequest,
    RejectEmailResponse,
    SendReplyRequest,
    SendReplyResponse,
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


@router.post("/send-reply")
def send_reply(
    req: SendReplyRequest,
    gmail_service: GmailOAuthService = Depends(get_gmail_service),
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Send a quick reply email to a recipient."""
    try:
        msg_id, thread_id = gmail_service.safe_send_email(
            recipient=req.recipient,
            subject=req.subject,
            body_text=req.body_text,
            thread_id=req.thread_id or None,
        )
        record = tracker.create_record(
            company_name=req.recipient.split("@")[0] if "@" in req.recipient else req.recipient,
            email=req.recipient,
            subject=req.subject,
            body_preview=req.body_text,
            status="SENT",
            thread_id=thread_id,
            gmail_message_id=msg_id,
            is_reply=True,
        )
        return SendReplyResponse(status="SENT", gmail_message_id=msg_id, tracker_id=record["id"])
    except Exception as e:
        logger.error("Failed to send reply: %s", e)
        raise HTTPException(500, f"Failed to send reply: {e}")


# ── Campaign Management ──────────────────────────────────────────────────────


@router.get("/campaigns", response_model=list)
def list_campaigns(
    status: str | None = None,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """List all campaigns, optionally filtered by status."""
    q = tracker.db.table("mail_agent_campaigns").select("*").order("created_at", desc=True)
    if status:
        q = q.eq("status", status)
    resp = q.execute()
    return resp.data or []


@router.get("/campaigns/{campaign_id}", response_model=dict)
def get_campaign(
    campaign_id: str,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Get a single campaign with its stats."""
    resp = tracker.db.table("mail_agent_campaigns").select("*").eq("id", campaign_id).limit(1).execute()
    rows = resp.data or []
    if not rows:
        raise HTTPException(404, "Campaign not found")
    campaign = rows[0]

    # Get linked emails count by status
    tracker_resp = tracker.db.table(tracker.table).select("status").eq("campaign_id", campaign_id).execute()
    emails = tracker_resp.data or []
    campaign["sent_count"] = sum(1 for e in emails if e.get("status") == "SENT")
    campaign["reply_count"] = sum(1 for e in emails if e.get("status") == "REPLY")
    campaign["bounce_count"] = sum(1 for e in emails if e.get("status") == "FAILED")
    campaign["total_leads"] = len(emails)
    return campaign


@router.post("/campaigns", response_model=dict)
def create_campaign(
    req: CampaignCreate,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Create a new campaign."""
    import uuid
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    record = {
        "id": str(uuid.uuid4()),
        "name": req.name,
        "description": req.description,
        "target_audience": req.target_audience,
        "status": "ACTIVE",
        "start_date": req.start_date or now,
        "end_date": req.end_date,
        "created_at": now,
        "updated_at": now,
    }
    tracker.db.table("mail_agent_campaigns").insert(record).execute()
    return record


@router.patch("/campaigns/{campaign_id}", response_model=dict)
def update_campaign(
    campaign_id: str,
    req: CampaignUpdate,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Update a campaign."""
    existing = tracker.db.table("mail_agent_campaigns").select("*").eq("id", campaign_id).limit(1).execute()
    if not existing.data:
        raise HTTPException(404, "Campaign not found")

    payload = {"updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    if req.name is not None:
        payload["name"] = req.name
    if req.description is not None:
        payload["description"] = req.description
    if req.target_audience is not None:
        payload["target_audience"] = req.target_audience
    if req.status is not None:
        payload["status"] = req.status
    if req.start_date is not None:
        payload["start_date"] = req.start_date
    if req.end_date is not None:
        payload["end_date"] = req.end_date

    tracker.db.table("mail_agent_campaigns").update(payload).eq("id", campaign_id).execute()
    updated = tracker.db.table("mail_agent_campaigns").select("*").eq("id", campaign_id).limit(1).execute()
    return updated.data[0]


@router.delete("/campaigns/{campaign_id}")
def delete_campaign(
    campaign_id: str,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Delete a campaign (does not delete linked emails)."""
    tracker.db.table("mail_agent_campaigns").delete().eq("id", campaign_id).execute()
    return {"message": "Campaign deleted"}


@router.post("/campaigns/{campaign_id}/assign")
def assign_to_campaign(
    campaign_id: str,
    req: CampaignAssignRequest,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Assign tracker emails to a campaign."""
    # Verify campaign exists
    existing = tracker.db.table("mail_agent_campaigns").select("id").eq("id", campaign_id).limit(1).execute()
    if not existing.data:
        raise HTTPException(404, "Campaign not found")

    if req.tracker_ids:
        tracker.db.table(tracker.table).update({"campaign_id": campaign_id}).in_("id", req.tracker_ids).execute()

    return {"message": f"Assigned {len(req.tracker_ids)} emails to campaign", "campaign_id": campaign_id}


# ── Lead Notes ──────────────────────────────────────────────────────────────


@router.get("/leads/{lead_id}/notes", response_model=list)
def list_lead_notes(
    lead_id: str,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """List all notes for a lead."""
    resp = tracker.db.table("lead_notes").select("*").eq("lead_id", lead_id).order("created_at", desc=True).execute()
    return resp.data or []


@router.post("/leads/{lead_id}/notes", response_model=dict)
def create_lead_note(
    lead_id: str,
    req: LeadNoteCreate,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Add a note to a lead."""
    import uuid
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    record = {
        "id": str(uuid.uuid4()),
        "lead_id": lead_id,
        "note_text": req.note_text,
        "note_type": req.note_type,
        "created_by": "user",
        "created_at": now,
        "updated_at": now,
    }
    tracker.db.table("lead_notes").insert(record).execute()
    return record


@router.delete("/leads/{lead_id}/notes/{note_id}")
def delete_lead_note(
    lead_id: str,
    note_id: str,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Delete a lead note."""
    tracker.db.table("lead_notes").delete().eq("id", note_id).eq("lead_id", lead_id).execute()
    return {"message": "Note deleted"}


@router.get("/leads/{lead_id}/activity")
def get_lead_activity(
    lead_id: str,
    ingestion: LeadIngestionService = Depends(get_lead_ingestion),
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Get full activity timeline for a lead — emails, notes, compliance events."""
    lead = ingestion.fetch_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")

    lead_email = lead.get("email") or lead.get("Email") or ""
    lead_name = lead.get("name") or lead.get("company") or ""

    activity = []

    # Tracker emails related to this lead
    if lead_email:
        q = tracker.db.table(tracker.table).select("*").eq("email", lead_email).order("created_at", desc=True).limit(20)
        for r in (q.execute().data or []):
            activity.append({
                "activity_type": "tracker",
                "timestamp": r.get("created_at", ""),
                "description": f"Email {r.get('status', 'PENDING').lower()}: {r.get('email_subject', '(no subject)')}",
                "details": {"status": r.get("status"), "subject": r.get("email_subject", ""), "tracker_id": r.get("id")},
            })

    # Lead notes
    notes_resp = tracker.db.table("lead_notes").select("*").eq("lead_id", lead_id).order("created_at", desc=True).limit(20)
    for n in (notes_resp.execute().data or []):
        activity.append({
            "activity_type": "note",
            "timestamp": n.get("created_at", ""),
            "description": f"{n.get('note_type', 'general').title()} note: {n.get('note_text', '')[:100]}",
            "details": {"note_id": n.get("id"), "note_type": n.get("note_type"), "text": n.get("note_text", "")},
        })

    # Compliance events
    if lead_email:
        comp_resp = tracker.db.table("mail_agent_compliance").select("*").eq("email", lead_email).order("created_at", desc=True).limit(10)
        for c in (comp_resp.execute().data or []):
            activity.append({
                "activity_type": "compliance",
                "timestamp": c.get("created_at", ""),
                "description": f"Compliance event: {c.get('event_type', 'unknown')}",
                "details": {"event_type": c.get("event_type"), "source": c.get("source", "")},
            })

    activity.sort(key=lambda x: x["timestamp"], reverse=True)
    return activity


# ── Lead Scoring ─────────────────────────────────────────────────────────────


@router.get("/leads/{lead_id}/score", response_model=LeadScore)
def get_lead_score(
    lead_id: str,
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Get the latest AI score for a specific lead."""
    resp = (
        tracker.db.table("lead_scores")
        .select("*")
        .eq("lead_id", lead_id)
        .order("scored_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise HTTPException(404, "No score available for this lead")
    return LeadScore(**rows[0])


@router.get("/leads/scores", response_model=LeadScoreResponse)
def get_lead_scores(
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Get latest scores for all scored leads."""
    resp = tracker.db.table("lead_scores").select("*").order("scored_at", desc=True).execute()
    rows = resp.data or []
    # Keep only the latest score per lead
    seen = set()
    unique = []
    for r in rows:
        lid = r.get("lead_id")
        if lid not in seen:
            seen.add(lid)
            unique.append(LeadScore(**r))
    return LeadScoreResponse(scores=unique, message=f"{len(unique)} leads scored")


@router.post("/leads/score", response_model=LeadScoreResponse)
async def score_leads(
    req: LeadScoreRequest,
    ingestion: LeadIngestionService = Depends(get_lead_ingestion),
    email_gen: EmailGeneratorService = Depends(get_email_generator),
    tracker: MailTrackerService = Depends(get_mail_tracker),
):
    """Score leads using AI prioritization. If no lead_ids provided, scores all unscored leads."""
    import datetime as dt

    # Determine which leads to score
    if req.lead_ids:
        raw = []
        for lid in req.lead_ids:
            lead = ingestion.fetch_lead_by_id(lid)
            if lead:
                raw.append(lead)
    else:
        raw = ingestion.fetch_pending_leads(limit=200, offset=0)

    if not raw:
        return LeadScoreResponse(scores=[], message="No leads to score")

    results = []
    now = dt.datetime.now(dt.timezone.utc).isoformat()

    for lead in raw:
        lead_id = lead.get("id")
        if not lead_id:
            continue

        company_name = lead.get("name") or lead.get("company") or "Unknown"
        context = lead.get("context") or lead.get("Context") or ""

        # Score via LLM
        score = email_gen.prioritize(company_name, context)

        # Store score
        score_record = {
            "lead_id": lead_id,
            "company_name": company_name,
            "score": round(score * 100, 1),  # 0-100 scale
            "reasoning": f"AI-scored {score:.2f} based on context analysis",
            "scored_at": now,
        }

        # Upsert: delete old score then insert new one
        tracker.db.table("lead_scores").delete().eq("lead_id", lead_id).execute()
        tracker.db.table("lead_scores").insert(score_record).execute()

        results.append(LeadScore(**score_record))

    return LeadScoreResponse(
        scores=results,
        message=f"Scored {len(results)} leads",
    )