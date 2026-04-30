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
