'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import * as api from '@/lib/api';
import DashboardView from '@/components/views/DashboardView';
import ReviewView from '@/components/views/ReviewView';
import SentView from '@/components/views/SentView';
import BatchesView from '@/components/views/BatchesView';
import LogsView from '@/components/views/LogsView';
import PerformanceView from '@/components/views/PerformanceView';
import SettingsView from '@/components/views/SettingsView';
import TemplatesView from '@/components/views/TemplatesView';
import ComplianceView from '@/components/views/ComplianceView';
import WarmupView from '@/components/views/WarmupView';
import ExecutionView from '@/components/views/ExecutionView';
import LeadsView from '@/components/views/LeadsView';

type Tab = keyof typeof tabTitles;

const tabTitles = {
  dashboard: 'Dashboard Summary', review: 'Human Review Queue', sent: 'Sent Email History',
  batches: 'Batch History', logs: 'System Execution Logs', performance: 'Performance Analytics',
  settings: 'Agent Configuration', templates: 'Email Templates', compliance: 'Compliance Tracker',
  warmup: 'Warmup Dashboard', execution: 'Agent Execution Engine', leads: 'Lead Management',
} as const;

const sidebarItems: { id: Tab; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard Summary' }, { id: 'review', label: 'Review Queue' },
  { id: 'sent', label: 'Sent History' }, { id: 'batches', label: 'Batch History' },
  { id: 'logs', label: 'System Logs' }, { id: 'performance', label: 'Performance' },
  { id: 'settings', label: 'Settings' }, { id: 'templates', label: 'Templates' },
  { id: 'compliance', label: 'Compliance' }, { id: 'warmup', label: 'Warmup' },
  { id: 'execution', label: 'Agent Execution' }, { id: 'leads', label: 'Lead Management' },
];

function NavIcon({ id }: { id: string }) {
  const s = { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
  const map: Record<string, JSX.Element> = {
    dashboard: <><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></>,
    review: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></>,
    sent: <><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></>,
    batches: <><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></>,
    logs: <><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></>,
    performance: <><path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></>,
    templates: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></>,
    compliance: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></>,
    warmup: <><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></>,
  };
  return <svg {...s}>{map[id] || map.dashboard}</svg>;
}

export default function Dashboard() {
  const [authenticated, setAuthenticated] = useState(false);
  const [showAuthGate, setShowAuthGate] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>('dashboard');
  const [queueBadge, setQueueBadge] = useState(0);
  const [toasts, setToasts] = useState<{ id: number; msg: string }[]>([]);
  const tid = useRef(0);

  const toast = useCallback((msg: string) => {
    const id = ++tid.current;
    setToasts(p => [...p, { id, msg }]);
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 3000);
  }, []);

  useEffect(() => {
    api.auth.status().then(r => { setAuthenticated(r.authenticated); setShowAuthGate(false); }).catch(() => setShowAuthGate(false));
  }, []);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement).tagName)) return;
      const m: Record<string, Tab> = { '1': 'dashboard', '2': 'review', '3': 'sent', '4': 'batches', '5': 'logs', '6': 'performance', '7': 'settings', '8': 'templates', '9': 'compliance' };
      if (m[e.key]) { e.preventDefault(); setActiveTab(m[e.key]); }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);

  if (showAuthGate) return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}><div className="cohere-pulse" style={{ width: 32, height: 32 }}></div></div>;

  if (!authenticated) return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', backgroundColor: 'var(--off-white-bg)' }}>
      <div className="auth-card">
        <div className="intro-orb"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg></div>
        <h1 className="display-serif" style={{ fontSize: 28, color: 'var(--matte-black)', marginBottom: 16 }}>Connect your Workspace</h1>
        <p style={{ color: 'var(--muted-slate)', fontSize: 15, marginBottom: 32 }}>Connect the Google account for sending outreach emails.</p>
        <a href={api.auth.googleUrl()} className="btn btn-solid" style={{ width: '100%', justifyContent: 'center', height: 48, fontSize: 15, textDecoration: 'none' }}>Connect to Google</a>
      </div>
    </div>
  );

  return (
    <div className="app">
      <div className="sidebar">
        <div className="logo display-serif"><div className="logo-icon"><div className="logo-box">M</div></div><span>MailAgent</span></div>
        {sidebarItems.map(item => (
          <a key={item.id} className={`nav-item ${activeTab === item.id ? 'active' : ''}`} onClick={() => setActiveTab(item.id)}>
            <span className="nav-icon"><NavIcon id={item.id} /></span>
            <span>{item.label}</span>
            {item.id === 'review' && queueBadge > 0 && <span className="badge mono-label" style={{ marginLeft: 'auto', marginRight: 8 }}>{queueBadge}</span>}
          </a>
        ))}
      </div>

      <div className="header">
        <h1 className="page-title display-serif">{tabTitles[activeTab]}</h1>
        <div className="header-actions">
          <span className="auth-status connected mono-label">GMAIL CONNECTED</span>
          <button className="btn btn-light" onClick={() => window.location.href = api.auth.googleUrl()}>Login via Google</button>
          <button className="btn btn-ghost" style={{ color: '#ef4444', border: '1px solid #fecaca', fontSize: 11, padding: '6px 14px' }} onClick={async () => { try { await api.auth.logout(); } catch {} setAuthenticated(false); }}>Logout</button>
        </div>
      </div>

      <div className="main">
        {activeTab === 'dashboard' && <DashView toast={toast} setBadge={setQueueBadge} />}
        {activeTab === 'review' && <RevView toast={toast} setBadge={setQueueBadge} />}
        {activeTab === 'sent' && <SentV toast={toast} />}
        {activeTab === 'batches' && <BatchV />}
        {activeTab === 'logs' && <LogV />}
        {activeTab === 'performance' && <PerfV />}
        {activeTab === 'settings' && <SetV toast={toast} />}
        {activeTab === 'templates' && <TmplV toast={toast} />}
        {activeTab === 'compliance' && <CompV />}
        {activeTab === 'warmup' && <WarmV />}
        {activeTab === 'execution' && <ExecV toast={toast} onClose={() => setActiveTab('dashboard')} />}
        {activeTab === 'leads' && <LeadV toast={toast} />}
      </div>

      {toasts.map(t => <div key={t.id} className="toast show"><span>{t.msg}</span></div>)}
    </div>
  );
}

// ── Data-loading wrapper components ──

function DashView({ toast, setBadge }: { toast: (s: string) => void; setBadge: (n: number) => void }) {
  const [stats, setStats] = useState({ total: 0, pending: 0, sent: 0, failed: 0 });
  const [running, setRunning] = useState(false);
  const [leads, setLeads] = useState<any[]>([]);
  const [page, setPage] = useState(1);

  useEffect(() => { api.dashboard.summary().then(s => { setStats(s); setBadge(s.pending || 0); }).catch(() => {});
    api.langgraph.status().then(a => setRunning(a.workflow_status === 'RUNNING')).catch(() => {});
    api.leads.list(10, (page - 1) * 10).then(setLeads).catch(() => {}); }, [page, setBadge]);

  return <DashboardView stats={stats} agentRunning={running} leads={leads} leadsPage={page} onPrevPage={() => setPage(p => Math.max(1, p - 1))} onNextPage={() => setPage(p => p + 1)} onInvoke={async () => { try { await api.langgraph.runBatch(); toast('Agent batch triggered'); setRunning(true); setTimeout(() => setRunning(false), 5000); } catch (e: any) { toast(e.message); } }} />;
}

function RevView({ toast, setBadge }: { toast: (s: string) => void; setBadge: (n: number) => void }) {
  const [items, setItems] = useState<any[]>([]);
  const [sid, setSid] = useState<string | null>(null);
  const [draft, setDraft] = useState<any>(null);
  const [sub, setSub] = useState('');
  const [body, setBody] = useState('');
  const [bulk, setBulk] = useState<Set<string>>(new Set());

  const load = useCallback(() => { api.tracker.list('PENDING').then(d => { setItems(d); setBadge(d.length); }).catch(() => {}); }, [setBadge]);
  useEffect(() => { load(); }, [load]);

  const select = async (item: any) => {
    try { const d = await api.tracker.get(item.id); setDraft(d); setSid(d.id); setSub(d.email_subject || ''); setBody(d.email_body_preview || ''); } catch {}
  };

  return <ReviewView items={items} selectedId={sid} onSelect={select} bulkIds={bulk} onToggleBulk={id => setBulk(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; })} onBulkApprove={async () => { try { await api.actions.bulkApprove(Array.from(bulk)); toast(`${bulk.size} approved`); setBulk(new Set()); load(); } catch (e: any) { toast(e.message); } }} onBulkReject={async () => { const r = prompt('Reason:'); if (!r) return; try { await api.actions.bulkReject(Array.from(bulk), r); toast(`${bulk.size} rejected`); setBulk(new Set()); load(); } catch (e: any) { toast(e.message); } }} onClearBulk={() => setBulk(new Set())} selectedDraft={draft} editorSubject={sub} editorBody={body} onSubjectChange={setSub} onBodyChange={setBody} onApprove={async () => { if (!draft) return; try { await api.actions.approve(draft.id); toast('Approved'); setDraft(null); setSid(null); load(); } catch (e: any) { toast(e.message); } }} onReject={async () => { if (!draft) return; const r = prompt('Reason:'); if (r === null) return; try { await api.actions.reject(draft.id, r); toast('Rejected'); setDraft(null); setSid(null); load(); } catch (e: any) { toast(e.message); } }} onRefresh={load} />;
}

function SentV({ toast }: { toast: (s: string) => void }) {
  const [items, setItems] = useState<any[]>([]);
  const loadSent = useCallback(() => { api.tracker.list('SENT').then(setItems).catch(() => {}); }, []);
  useEffect(() => { loadSent(); }, [loadSent]);
  return <SentView items={items} onCheckReplies={async () => { try { const r = await api.actions.checkReplies(); toast(`Found ${r.detected} replies`); loadSent(); } catch (e: any) { toast(e.message); } }} onReply={async (to, subject, body) => { try { await api.actions.sendReply(to, subject, body); toast('Reply sent'); loadSent(); } catch (e: any) { toast(e.message); } }} />;
}

function BatchV() {
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => { api.langgraph.batches().then(setItems).catch(() => {}); }, []);
  return <BatchesView items={items} />;
}

function LogV() {
  const [items, setItems] = useState<any[]>([]);
  const [s, setS] = useState('');
  useEffect(() => { api.langgraph.logs(s || undefined).then(setItems).catch(() => {}); }, [s]);
  return <LogsView items={items} search={s} onSearchChange={setS} onRefresh={() => api.langgraph.logs(s || undefined).then(setItems).catch(() => {})} />;
}

function PerfV() {
  const [m, setM] = useState<any[]>([]);
  const [r, setR] = useState<any>(null);
  const load = useCallback(() => { Promise.all([api.autonomous.metrics(7), api.langgraph.executionReport(50)]).then(([a, b]) => { setM(a); setR(b); }).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);
  return <PerformanceView metrics={m} report={r} onRefresh={load} />;
}

function SetV({ toast }: { toast: (s: string) => void }) {
  const [running, setRunning] = useState(false);
  const [last, setLast] = useState<string | null>(null);
  const [th, setTh] = useState(0.85);
  const [bs, setBs] = useState(10);
  useEffect(() => { api.autonomous.schedulerStatus().then(s => { setRunning(s.is_running); setLast(s.last_run); }).catch(() => {}); }, []);
  return <SettingsView schedulerRunning={running} schedulerLastRun={last} onToggleScheduler={async () => { try { running ? await api.autonomous.schedulerStop() : await api.autonomous.schedulerStart(); const s = await api.autonomous.schedulerStatus(); setRunning(s.is_running); setLast(s.last_run); toast(`Scheduler ${s.is_running ? 'started' : 'stopped'}`); } catch (e: any) { toast(e.message); } }} onRunNow={async () => { try { await api.autonomous.schedulerRunNow(); toast('Started'); } catch (e: any) { toast(e.message); } }} threshold={th} onThresholdChange={setTh} batchSize={bs} onBatchSizeChange={setBs} onSave={async () => { try { await api.autonomous.updateConfig({ auto_send_threshold: th, batch_size: bs }); toast('Saved'); } catch (e: any) { toast(e.message); } }} />;
}

function TmplV({ toast }: { toast: (s: string) => void }) {
  const [list, setList] = useState<any[]>([]);
  const [s, setS] = useState('');
  const [sel, setSel] = useState<any>(null);
  const [f, setF] = useState({ name: '', subject: '', body: '' });
  useEffect(() => { api.templates.list(s || undefined).then(setList).catch(() => {}); }, [s]);
  return <TemplatesView templates={list} search={s} onSearchChange={setS} selectedTemplate={sel} onSelect={t => { setSel(t); setF({ name: t.name, subject: t.subject, body: t.body }); }} onNew={() => { setSel({ id: null }); setF({ name: '', subject: '', body: '' }); }} form={f} onFormChange={(k, v) => setF(p => ({ ...p, [k]: v }))} onSave={async () => { try { sel?.id ? await api.templates.update(sel.id, f) : await api.templates.create(f as any); toast('Saved'); api.templates.list(s || undefined).then(setList); } catch (e: any) { toast(e.message); } }} onDelete={async () => { if (!sel?.id || !confirm('Delete?')) return; try { await api.templates.delete(sel.id); toast('Deleted'); setSel(null); setF({ name: '', subject: '', body: '' }); api.templates.list(s || undefined).then(setList); } catch (e: any) { toast(e.message); } }} />;
}

function CompV() {
  const [sum, setSum] = useState<any>({});
  const [items, setItems] = useState<any[]>([]);
  const load = useCallback(() => { Promise.all([api.compliance.summary(), api.compliance.list()]).then(([s, l]) => { setSum(s); setItems(l); }).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);
  return <ComplianceView summary={sum} items={items} onRefresh={load} />;
}

function WarmV() {
  const [d, setD] = useState<any>(null);
  useEffect(() => { api.warmup.get().then(setD).catch(() => {}); }, []);
  return <WarmupView data={d} />;
}

function LeadV({ toast }: { toast: (s: string) => void }) {
  const [items, setItems] = useState<any[]>([]);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [ingesting, setIngesting] = useState(false);
  const perPage = 10;

  const load = useCallback(() => {
    api.leads.list(perPage, (page - 1) * perPage).then(setItems).catch(() => {});
  }, [page]);

  useEffect(() => { load(); }, [load]);

  return <LeadsView
    items={items}
    page={page}
    totalPages={Math.ceil(Math.max(items.length, 1) / perPage)}
    search={search}
    onSearchChange={setSearch}
    onPrevPage={() => setPage(p => Math.max(1, p - 1))}
    onNextPage={() => setPage(p => p + 1)}
    onIngest={async () => {
      setIngesting(true);
      try { const r = await api.leads.ingest(); toast(`Ingested ${r.leads_discovered} leads`); load(); }
      catch (e: any) { toast(e.message); }
      finally { setIngesting(false); }
    }}
    ingesting={ingesting}
    onRefresh={load}
  />;
}

function ExecV({ toast, onClose }: { toast: (s: string) => void; onClose: () => void }) {
  const [viz, setViz] = useState('discover');
  const [leads, setLeads] = useState<any[]>([]);
  const [email, setEmail] = useState({ subject: '', to: '', body: '' });
  const [processing, setProcessing] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(api.langgraph.runBatchStream(), { method: 'POST' });
        const reader = r.body!.getReader();
        const d = new TextDecoder(); let buf = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += d.decode(value, { stream: true });
          for (const line of buf.split('\n').filter(l => l.startsWith('data: '))) {
            try {
              const ev = JSON.parse(line.slice(6));
              if (ev.type === 'LEAD_START') { setViz('generate'); setEmail({ subject: 'Synthesizing...', to: ev.email || '', body: `Thinking about ${ev.name || 'lead'}...` }); }
              if (ev.type === 'LEAD_RESULT') { if (ev.subject) setEmail({ subject: ev.subject, to: ev.to || '', body: ev.body_preview || '' }); if (ev.confidence !== undefined) setViz('quality'); toast(`→ ${ev.name || ''}: ${ev.action || ev.status}`); }
              if (ev.type === 'PHASE' && ev.phase === 'prioritize' && ev.status === 'completed' && ev.leads) { setLeads(ev.leads); setViz('prioritize'); }
              if (ev.type === 'DONE') { setViz('complete'); toast(`Batch: ${ev.total_leads || 0} leads`); }
            } catch {}
          }
          buf = buf.split('\n').pop() || '';
        }
      } catch (e: any) { toast(e.message); }
      await new Promise(r => setTimeout(r, 2000));
      setProcessing(false);
      onClose();
    })();
  }, []);

  return <ExecutionView execViz={viz} execLeads={leads} execEmail={email} onClose={onClose} processingExec={processing} />;
}
