const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000/api';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Auth ──────────────────────────────────────────────────────────────

export const auth = {
  status: () => fetchJson<{ authenticated: boolean; has_refresh_token?: boolean; expired?: boolean }>(`${API_BASE}/auth/status`),
  logout: () => fetchJson<{ message: string }>(`${API_BASE}/auth/logout`, { method: 'POST' }),
  googleUrl: () => `${API_BASE}/auth/google`,
};

// ── Dashboard ─────────────────────────────────────────────────────────

export const dashboard = {
  summary: () => fetchJson<{ total: number; pending: number; sent: number; failed: number; rejected: number }>(`${API_BASE}/mail-agent/dashboard/summary`),
  config: () => fetchJson<{ supabase_url: string; supabase_anon_key: string; leads_table: string; tracker_table: string }>(`${API_BASE}/mail-agent/config/public`),
};

// ── Leads ─────────────────────────────────────────────────────────────

export const leads = {
  list: (limit = 10, offset = 0) =>
    fetchJson<any[]>(`${API_BASE}/mail-agent/leads?limit=${limit}&offset=${offset}`),
  get: (id: string) => fetchJson<any>(`${API_BASE}/mail-agent/leads/${id}`),
  ingest: () =>
    fetchJson<{ status: string; batch_id: string; leads_discovered: number }>(`${API_BASE}/mail-agent/leads/ingest`, { method: 'POST' }),
  exportCsvUrl: () => `${API_BASE}/mail-agent/leads/export/csv`,
};

// ── Tracker / Review Queue ────────────────────────────────────────────

export const tracker = {
  list: (status?: string, limit = 100, offset = 0) => {
    let url = `${API_BASE}/mail-agent/tracker?limit=${limit}&offset=${offset}`;
    if (status) url += `&status=${status}`;
    return fetchJson<any[]>(url);
  },
  get: (id: string) => fetchJson<any>(`${API_BASE}/mail-agent/tracker/${id}`),
  update: (id: string, data: { subject?: string; body_text?: string }) =>
    fetchJson<any>(`${API_BASE}/mail-agent/tracker/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  context: (id: string) => fetchJson<any>(`${API_BASE}/mail-agent/tracker/${id}/context`),
};

// ── Approve / Reject / Regenerate ─────────────────────────────────────

export const actions = {
  approve: (tracker_id: string) =>
    fetchJson<any>(`${API_BASE}/mail-agent/approve`, {
      method: 'POST',
      body: JSON.stringify({ tracker_id }),
    }),
  reject: (tracker_id: string, reason: string) =>
    fetchJson<any>(`${API_BASE}/mail-agent/reject`, {
      method: 'POST',
      body: JSON.stringify({ tracker_id, reason }),
    }),
  regenerate: (tracker_id: string, feedback: string) =>
    fetchJson<any>(`${API_BASE}/mail-agent/regenerate`, {
      method: 'POST',
      body: JSON.stringify({ tracker_id, feedback }),
    }),
  bulkApprove: (tracker_ids: string[]) =>
    fetchJson<any>(`${API_BASE}/mail-agent/bulk-approve`, {
      method: 'POST',
      body: JSON.stringify({ tracker_ids }),
    }),
  bulkReject: (tracker_ids: string[], reason: string) =>
    fetchJson<any>(`${API_BASE}/mail-agent/bulk-reject`, {
      method: 'POST',
      body: JSON.stringify({ tracker_ids, reason }),
    }),
  checkReplies: () =>
    fetchJson<{ detected: number; replies: any[] }>(`${API_BASE}/mail-agent/check-replies`, { method: 'POST' }),
  sendReply: (recipient: string, subject: string, body_text: string, thread_id?: string) =>
    fetchJson<{ status: string; gmail_message_id: string; tracker_id: string }>(`${API_BASE}/mail-agent/send-reply`, {
      method: 'POST',
      body: JSON.stringify({ recipient, subject, body_text, thread_id: thread_id || '' }),
    }),
};

// ── Templates ─────────────────────────────────────────────────────────

export const templates = {
  list: (search?: string) => {
    let url = `${API_BASE}/mail-agent/templates`;
    if (search) url += `?search=${encodeURIComponent(search)}`;
    return fetchJson<any[]>(url);
  },
  get: (id: string) => fetchJson<any>(`${API_BASE}/mail-agent/templates/${id}`),
  create: (data: { name: string; subject: string; body: string }) =>
    fetchJson<any>(`${API_BASE}/mail-agent/templates`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  update: (id: string, data: { name?: string; subject?: string; body?: string }) =>
    fetchJson<any>(`${API_BASE}/mail-agent/templates/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  delete: (id: string) =>
    fetchJson<any>(`${API_BASE}/mail-agent/templates/${id}`, { method: 'DELETE' }),
};

// ── LangGraph / Agent ──────────────────────────────────────────────────

export const langgraph = {
  status: () =>
    fetchJson<{
      workflow_status: string;
      avg_ai_confidence: number;
      total_ai_decisions: number;
      queue_status: Record<string, number>;
    }>(`${API_BASE}/langgraph-agent/status`),
  logs: (tracker_id?: string, limit = 50) => {
    let url = `${API_BASE}/langgraph-agent/logs?limit=${limit}`;
    if (tracker_id) url += `&tracker_id=${tracker_id}`;
    return fetchJson<any[]>(url);
  },
  batches: (limit = 20) =>
    fetchJson<any[]>(`${API_BASE}/langgraph-agent/batches?limit=${limit}`),
  executionReport: (limit = 50) =>
    fetchJson<any>(`${API_BASE}/langgraph-agent/execution-report?limit=${limit}`),
  runBatchStream: () => `${API_BASE}/langgraph-agent/run-autonomous-batch/stream`,
  runBatch: () =>
    fetchJson<any>(`${API_BASE}/langgraph-agent/run-autonomous-batch`, { method: 'POST' }),
  mermaid: () =>
    fetchJson<{ mermaid_diagram: string }>(`${API_BASE}/langgraph-agent/visualize/mermaid`),
};

// ── Autonomous Agent ─────────────────────────────────────────────────

export const autonomous = {
  metrics: (days = 7) =>
    fetchJson<any[]>(`${API_BASE}/autonomous-agent/metrics/daily?days=${days}`),
  metricsSummary: () => fetchJson<any>(`${API_BASE}/autonomous-agent/metrics/summary`),
  schedulerStatus: () =>
    fetchJson<{ is_running: boolean; last_run: string | null }>(`${API_BASE}/autonomous-agent/scheduler/status`),
  schedulerStart: () =>
    fetchJson<any>(`${API_BASE}/autonomous-agent/scheduler/start`, { method: 'POST' }),
  schedulerStop: () =>
    fetchJson<any>(`${API_BASE}/autonomous-agent/scheduler/stop`, { method: 'POST' }),
  schedulerRunNow: () =>
    fetchJson<any>(`${API_BASE}/autonomous-agent/scheduler/run-now`, { method: 'POST' }),
  updateConfig: (data: { auto_send_threshold: number; batch_size: number }) =>
    fetchJson<any>(`${API_BASE}/autonomous-agent/config`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

// ── Compliance ───────────────────────────────────────────────────────

export const compliance = {
  summary: () => fetchJson<any>(`${API_BASE}/mail-agent/compliance/summary`),
  list: () => fetchJson<any[]>(`${API_BASE}/mail-agent/compliance/list`),
};

// ── Warmup ───────────────────────────────────────────────────────────

export const warmup = {
  get: () => fetchJson<any>(`${API_BASE}/mail-agent/warmup`),
};

// ── Campaigns ─────────────────────────────────────────────────────────

export const campaigns = {
  list: (status?: string) => {
    let url = `${API_BASE}/mail-agent/campaigns`;
    if (status) url += `?status=${encodeURIComponent(status)}`;
    return fetchJson<any[]>(url);
  },
  get: (id: string) => fetchJson<any>(`${API_BASE}/mail-agent/campaigns/${id}`),
  create: (data: { name: string; description?: string; target_audience?: string; start_date?: string; end_date?: string }) =>
    fetchJson<any>(`${API_BASE}/mail-agent/campaigns`, { method: 'POST', body: JSON.stringify(data) }),
  update: (id: string, data: { name?: string; description?: string; status?: string; target_audience?: string }) =>
    fetchJson<any>(`${API_BASE}/mail-agent/campaigns/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  delete: (id: string) =>
    fetchJson<any>(`${API_BASE}/mail-agent/campaigns/${id}`, { method: 'DELETE' }),
  assign: (id: string, data: { lead_ids?: string[]; tracker_ids?: string[] }) =>
    fetchJson<any>(`${API_BASE}/mail-agent/campaigns/${id}/assign`, { method: 'POST', body: JSON.stringify(data) }),
};

// ── Lead Scoring ────────────────────────────────────────────────────────

export const scores = {
  list: () =>
    fetchJson<{ scores: any[]; message: string }>(`${API_BASE}/mail-agent/leads/scores`),
  get: (leadId: string) =>
    fetchJson<{ lead_id: string; score: number; reasoning: string; scored_at: string }>(`${API_BASE}/mail-agent/leads/${leadId}/score`),
  score: (lead_ids: string[]) =>
    fetchJson<{ scores: any[]; message: string }>(`${API_BASE}/mail-agent/leads/score`, {
      method: 'POST',
      body: JSON.stringify({ lead_ids }),
    }),
};

// ── Deep Research ──────────────────────────────────────────────────────

export const research = {
  uploadCsv: async (file: File) => {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${API_BASE}/research/upload-csv`, { method: 'POST', body: form });
    if (!res.ok) throw new Error((await res.json().catch(() => ({ detail: 'Upload failed' }))).detail);
    return res.json() as Promise<{ batch_id: string; total_leads: number; message: string }>;
  },
  single: (name: string, sector = '', size = '', lead_id = '') =>
    fetchJson<any>(`${API_BASE}/research/single`, {
      method: 'POST',
      body: JSON.stringify({ name, sector, size, lead_id }),
    }),
  batchProgress: (batchId: string) =>
    fetchJson<any>(`${API_BASE}/research/batch/${batchId}`),
  listBatches: () =>
    fetchJson<any[]>(`${API_BASE}/research/batches`),
  brief: (leadId: string) =>
    fetchJson<any>(`${API_BASE}/research/brief/${leadId}`),
  briefs: (confidenceMin = 0, limit = 50) =>
    fetchJson<any[]>(`${API_BASE}/research/briefs?confidence_min=${confidenceMin}&limit=${limit}`),
  briefByEmail: (email: string) =>
    fetchJson<any>(`${API_BASE}/research/brief/by-email/${encodeURIComponent(email)}`),
  config: () =>
    fetchJson<any>(`${API_BASE}/research/config`),
  health: () =>
    fetchJson<any>(`${API_BASE}/research/health`),
};

// ── Follow-ups ─────────────────────────────────────────────────────────

export const followUps = {
  rules: {
    list: () =>
      fetchJson<any[]>(`${API_BASE}/follow-ups/rules`),
    get: (id: string) =>
      fetchJson<any>(`${API_BASE}/follow-ups/rules/${id}`),
    create: (data: { name: string; delay_days?: number; max_follow_ups?: number; is_active?: boolean }) =>
      fetchJson<any>(`${API_BASE}/follow-ups/rules`, { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: { name?: string; delay_days?: number; max_follow_ups?: number; is_active?: boolean }) =>
      fetchJson<any>(`${API_BASE}/follow-ups/rules/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id: string) =>
      fetchJson<any>(`${API_BASE}/follow-ups/rules/${id}`, { method: 'DELETE' }),
  },
  pending: (limit = 100, offset = 0) =>
    fetchJson<any[]>(`${API_BASE}/follow-ups/pending?limit=${limit}&offset=${offset}`),
  list: (status?: string, limit = 100, offset = 0) => {
    let url = `${API_BASE}/follow-ups/list?limit=${limit}&offset=${offset}`;
    if (status) url += `&status=${status}`;
    return fetchJson<any[]>(url);
  },
  get: (id: string) =>
    fetchJson<any>(`${API_BASE}/follow-ups/${id}`),
  generate: (ruleId?: string, dryRun = false) => {
    let url = `${API_BASE}/follow-ups/generate?dry_run=${dryRun}`;
    if (ruleId) url += `&rule_id=${ruleId}`;
    return fetchJson<any>(url, { method: 'POST' });
  },
  approve: (id: string) =>
    fetchJson<any>(`${API_BASE}/follow-ups/${id}/approve`, { method: 'POST' }),
  skip: (id: string) =>
    fetchJson<any>(`${API_BASE}/follow-ups/${id}/skip`, { method: 'POST' }),
  summary: () =>
    fetchJson<{ total: number; pending: number; sent: number; skipped: number; failed: number; active_rules: number }>(`${API_BASE}/follow-ups/summary`),
};

// ── Scheduling ─────────────────────────────────────────────────

export const scheduling = {
  schedule: (tracker_id: string, scheduled_at: string) =>
    fetchJson<any>(`${API_BASE}/scheduling/schedule`, {
      method: 'POST',
      body: JSON.stringify({ tracker_id, scheduled_at }),
    }),
  list: (status?: string, limit = 100, offset = 0) => {
    let url = `${API_BASE}/scheduling/list?limit=${limit}&offset=${offset}`;
    if (status) url += `&status=${status}`;
    return fetchJson<any[]>(url);
  },
  get: (id: string) =>
    fetchJson<any>(`${API_BASE}/scheduling/${id}`),
  cancel: (id: string) =>
    fetchJson<any>(`${API_BASE}/scheduling/${id}`, { method: 'DELETE' }),
  processDue: () =>
    fetchJson<{ processed: number; results: any[] }>(`${API_BASE}/scheduling/process-due`, { method: 'POST' }),
  summary: () =>
    fetchJson<{ total: number; pending: number; sent: number; cancelled: number; failed: number }>(`${API_BASE}/scheduling/summary`),
};

// ── Analytics ────────────────────────────────────────────────────────

export const analytics = {
  report: (days = 30) =>
    fetchJson<any>(`${API_BASE}/analytics/report?days=${days}`),
  volume: (days = 30) =>
    fetchJson<any[]>(`${API_BASE}/analytics/volume?days=${days}`),
  statusBreakdown: () =>
    fetchJson<Record<string, number>>(`${API_BASE}/analytics/status-breakdown`),
  domains: () =>
    fetchJson<any[]>(`${API_BASE}/analytics/domains`),
  hourly: () =>
    fetchJson<any[]>(`${API_BASE}/analytics/hourly`),
  complianceBreakdown: () =>
    fetchJson<Record<string, number>>(`${API_BASE}/analytics/compliance-breakdown`),
  followUps: () =>
    fetchJson<any>(`${API_BASE}/analytics/follow-ups`),
  schedules: () =>
    fetchJson<any>(`${API_BASE}/analytics/schedules`),
};

export const notes = {
  list: (leadId: string) =>
    fetchJson<any[]>(`${API_BASE}/mail-agent/leads/${leadId}/notes`),
  create: (leadId: string, data: { note_text: string; note_type?: string }) =>
    fetchJson<any>(`${API_BASE}/mail-agent/leads/${leadId}/notes`, { method: 'POST', body: JSON.stringify(data) }),
  delete: (leadId: string, noteId: string) =>
    fetchJson<any>(`${API_BASE}/mail-agent/leads/${leadId}/notes/${noteId}`, { method: 'DELETE' }),
  activity: (leadId: string) =>
    fetchJson<any[]>(`${API_BASE}/mail-agent/leads/${leadId}/activity`),
};
