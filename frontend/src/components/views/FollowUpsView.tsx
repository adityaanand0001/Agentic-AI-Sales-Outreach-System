'use client';

import { useState, useEffect, useCallback } from 'react';
import * as api from '@/lib/api';

type Tab = 'rules' | 'pending' | 'history' | 'summary';

interface Rule {
  id: string; name: string; delay_days: number; max_follow_ups: number; is_active: boolean; created_at: string; updated_at: string;
}

interface FollowUp {
  id: string; rule_id: string; tracker_id: string; company_name: string; email: string; original_subject: string; original_sent_at: string;
  follow_up_number: number; scheduled_at: string; status: string; email_subject: string; email_body_preview: string; error: string; created_at: string;
}

export default function FollowUpsView({ toast }: { toast: (s: string) => void }) {
  const [tab, setTab] = useState<Tab>('pending');
  const [rules, setRules] = useState<Rule[]>([]);
  const [pending, setPending] = useState<FollowUp[]>([]);
  const [history, setHistory] = useState<FollowUp[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  // Rule form
  const [showRuleForm, setShowRuleForm] = useState(false);
  const [editRule, setEditRule] = useState<Rule | null>(null);
  const [ruleForm, setRuleForm] = useState({ name: '', delay_days: 3, max_follow_ups: 3, is_active: true });

  // Selected follow-up detail
  const [selectedFup, setSelectedFup] = useState<FollowUp | null>(null);

  const loadRules = useCallback(async () => {
    try { setRules(await api.followUps.rules.list()); } catch {}
  }, []);

  const loadPending = useCallback(async () => {
    try { setPending(await api.followUps.pending()); } catch {}
  }, []);

  const loadHistory = useCallback(async (status?: string) => {
    try { setHistory(await api.followUps.list(status)); } catch {}
  }, []);

  const loadSummary = useCallback(async () => {
    try { setSummary(await api.followUps.summary()); } catch {}
  }, []);

  useEffect(() => { loadRules(); loadPending(); loadSummary(); }, [loadRules, loadPending, loadSummary]);

  const handleTabChange = (t: Tab) => {
    setTab(t);
    setSelectedFup(null);
    if (t === 'history') loadHistory();
    if (t === 'summary') loadSummary();
    if (t === 'rules') loadRules();
    if (t === 'pending') loadPending();
  };

  const openNewRule = () => {
    setEditRule(null);
    setRuleForm({ name: '', delay_days: 3, max_follow_ups: 3, is_active: true });
    setShowRuleForm(true);
  };

  const openEditRule = (r: Rule) => {
    setEditRule(r);
    setRuleForm({ name: r.name, delay_days: r.delay_days, max_follow_ups: r.max_follow_ups, is_active: r.is_active });
    setShowRuleForm(true);
  };

  const saveRule = async () => {
    if (!ruleForm.name.trim()) { toast('Rule name is required'); return; }
    try {
      if (editRule) {
        await api.followUps.rules.update(editRule.id, ruleForm);
        toast('Rule updated');
      } else {
        await api.followUps.rules.create(ruleForm as any);
        toast('Rule created');
      }
      setShowRuleForm(false);
      loadRules();
    } catch (e: any) { toast(e.message); }
  };

  const deleteRule = async (id: string) => {
    if (!confirm('Delete this rule?')) return;
    try { await api.followUps.rules.delete(id); toast('Rule deleted'); loadRules(); } catch (e: any) { toast(e.message); }
  };

  const generateFollowUps = async () => {
    setLoading(true);
    try {
      const r = await api.followUps.generate();
      toast(r.message || `Generated ${r.created || 0} follow-ups`);
      loadPending();
      loadSummary();
    } catch (e: any) { toast(e.message); }
    finally { setLoading(false); }
  };

  const approveFollowUp = async (id: string) => {
    try {
      await api.followUps.approve(id);
      toast('Follow-up approved & sent');
      setSelectedFup(null);
      loadPending();
      loadSummary();
    } catch (e: any) { toast(e.message); }
  };

  const skipFollowUp = async (id: string) => {
    try {
      await api.followUps.skip(id);
      toast('Follow-up skipped');
      setSelectedFup(null);
      loadPending();
      loadSummary();
    } catch (e: any) { toast(e.message); }
  };

  return (
    <div className="followups-view">
      <div className="tabs" style={{ marginBottom: 20 }}>
        {(['pending', 'rules', 'history', 'summary'] as Tab[]).map(t => (
          <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => handleTabChange(t)}>
            {t === 'pending' ? `Pending (${summary?.pending ?? '...'})` : t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        {tab === 'pending' && (
          <button className="btn btn-solid" onClick={generateFollowUps} disabled={loading} style={{ height: 34, fontSize: 12 }}>
            {loading ? 'Generating...' : 'Generate Follow-ups'}
          </button>
        )}
        {tab === 'rules' && (
          <button className="btn btn-solid" onClick={openNewRule} style={{ height: 34, fontSize: 12 }}>+ New Rule</button>
        )}
      </div>

      {/* ── PENDING TAB ── */}
      {tab === 'pending' && (
        <div style={{ display: 'grid', gridTemplateColumns: selectedFup ? '1fr 380px' : '1fr', gap: 16 }}>
          <div>
            {pending.length === 0 ? (
              <div className="empty-state"><p>No pending follow-ups. Click "Generate Follow-ups" to scan for leads that need re-engagement.</p></div>
            ) : (
              <div className="table-container">
                <table className="data-table">
                  <thead><tr><th>Company</th><th>Email</th><th>Follow-up #</th><th>Scheduled</th><th>Subject</th><th>Status</th></tr></thead>
                  <tbody>
                    {pending.map(f => (
                      <tr key={f.id} className={selectedFup?.id === f.id ? 'selected' : ''} onClick={() => setSelectedFup(f)}>
                        <td><strong>{f.company_name}</strong></td>
                        <td className="mono-label">{f.email}</td>
                        <td>{f.follow_up_number}</td>
                        <td>{f.scheduled_at ? new Date(f.scheduled_at).toLocaleDateString() : '-'}</td>
                        <td className="text-ellipsis" style={{ maxWidth: 200 }}>{f.email_subject}</td>
                        <td><span className={`badge status-${f.status.toLowerCase()}`}>{f.status}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          {selectedFup && (
            <div className="detail-panel" style={{ position: 'sticky', top: 60, alignSelf: 'start' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <h3 style={{ margin: 0, fontSize: 16 }}>Follow-up Detail</h3>
                <button className="btn btn-ghost" style={{ padding: '2px 8px', fontSize: 16 }} onClick={() => setSelectedFup(null)}>&times;</button>
              </div>
              <div className="detail-field"><label>Company</label><span>{selectedFup.company_name}</span></div>
              <div className="detail-field"><label>Email</label><span>{selectedFup.email}</span></div>
              <div className="detail-field"><label>Follow-up #</label><span>{selectedFup.follow_up_number}</span></div>
              <div className="detail-field"><label>Original Sent</label><span>{selectedFup.original_sent_at ? new Date(selectedFup.original_sent_at).toLocaleString() : '-'}</span></div>
              <div className="detail-field"><label>Scheduled</label><span>{selectedFup.scheduled_at ? new Date(selectedFup.scheduled_at).toLocaleString() : '-'}</span></div>
              <div className="detail-field" style={{ gridColumn: '1 / -1' }}><label>Subject</label><span>{selectedFup.email_subject}</span></div>
              <div className="detail-field" style={{ gridColumn: '1 / -1' }}>
                <label>Body</label>
                <div className="email-preview" style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.5, maxHeight: 280, overflowY: 'auto', background: 'var(--off-white-bg)', padding: 12, borderRadius: 8 }}>
                  {selectedFup.email_body_preview || 'No preview available'}
                </div>
              </div>
              {selectedFup.error && <div className="detail-field" style={{ gridColumn: '1 / -1' }}><label>Error</label><span style={{ color: '#ef4444' }}>{selectedFup.error}</span></div>}
              <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                <button className="btn btn-solid" style={{ flex: 1, background: '#16a34a', borderColor: '#16a34a' }} onClick={() => approveFollowUp(selectedFup.id)}>Approve & Send</button>
                <button className="btn btn-light" style={{ flex: 1, color: '#6b7280' }} onClick={() => skipFollowUp(selectedFup.id)}>Skip</button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── RULES TAB ── */}
      {tab === 'rules' && (
        <div style={{ display: 'grid', gridTemplateColumns: showRuleForm ? '1fr 380px' : '1fr', gap: 16 }}>
          <div>
            {rules.length === 0 ? (
              <div className="empty-state"><p>No follow-up rules configured. Create a rule to automatically schedule follow-ups for unreplied leads.</p></div>
            ) : (
              <div className="table-container">
                <table className="data-table">
                  <thead><tr><th>Name</th><th>Delay (days)</th><th>Max Follow-ups</th><th>Active</th><th>Created</th><th>Actions</th></tr></thead>
                  <tbody>
                    {rules.map(r => (
                      <tr key={r.id}>
                        <td><strong>{r.name}</strong></td>
                        <td>{r.delay_days}</td>
                        <td>{r.max_follow_ups}</td>
                        <td><span className={`badge ${r.is_active ? 'status-approved' : 'status-failed'}`}>{r.is_active ? 'Active' : 'Inactive'}</span></td>
                        <td>{r.created_at ? new Date(r.created_at).toLocaleDateString() : '-'}</td>
                        <td>
                          <div style={{ display: 'flex', gap: 4 }}>
                            <button className="btn btn-ghost" style={{ padding: '2px 8px', fontSize: 11 }} onClick={() => openEditRule(r)}>Edit</button>
                            <button className="btn btn-ghost" style={{ padding: '2px 8px', fontSize: 11, color: '#ef4444' }} onClick={() => deleteRule(r.id)}>Delete</button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          {showRuleForm && (
            <div className="detail-panel" style={{ position: 'sticky', top: 60, alignSelf: 'start' }}>
              <h3 style={{ margin: '0 0 16px', fontSize: 16 }}>{editRule ? 'Edit Rule' : 'New Rule'}</h3>
              <div className="detail-field"><label>Name</label><input type="text" value={ruleForm.name} onChange={e => setRuleForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. Standard 3-day follow-up" /></div>
              <div className="detail-field"><label>Delay (days)</label><input type="number" min={1} value={ruleForm.delay_days} onChange={e => setRuleForm(p => ({ ...p, delay_days: Math.max(1, parseInt(e.target.value) || 1) }))} /></div>
              <div className="detail-field"><label>Max Follow-ups</label><input type="number" min={1} value={ruleForm.max_follow_ups} onChange={e => setRuleForm(p => ({ ...p, max_follow_ups: Math.max(1, parseInt(e.target.value) || 1) }))} /></div>
              <div className="detail-field">
                <label>Active</label>
                <label className="toggle-label">
                  <input type="checkbox" checked={ruleForm.is_active} onChange={e => setRuleForm(p => ({ ...p, is_active: e.target.checked }))} />
                  <span>{ruleForm.is_active ? 'Yes' : 'No'}</span>
                </label>
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                <button className="btn btn-solid" style={{ flex: 1 }} onClick={saveRule}>{editRule ? 'Update' : 'Create'}</button>
                <button className="btn btn-light" style={{ flex: 1 }} onClick={() => setShowRuleForm(false)}>Cancel</button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── HISTORY TAB ── */}
      {tab === 'history' && (
        <div>
          <div className="filter-bar" style={{ marginBottom: 12 }}>
            <select className="input" style={{ width: 180 }} onChange={e => loadHistory(e.target.value || undefined)} defaultValue="">
              <option value="">All Statuses</option>
              <option value="SENT">Sent</option>
              <option value="SKIPPED">Skipped</option>
              <option value="FAILED">Failed</option>
              <option value="PENDING">Pending</option>
            </select>
            <span className="mono-label" style={{ marginLeft: 8 }}>{history.length} records</span>
          </div>
          {history.length === 0 ? (
            <div className="empty-state"><p>No follow-up history yet.</p></div>
          ) : (
            <div className="table-container">
              <table className="data-table">
                <thead><tr><th>Company</th><th>Email</th><th>#</th><th>Subject</th><th>Scheduled</th><th>Status</th><th>Sent At</th></tr></thead>
                <tbody>
                  {history.map(f => (
                    <tr key={f.id} onClick={() => setSelectedFup(selectedFup?.id === f.id ? null : f)}>
                      <td><strong>{f.company_name}</strong></td>
                      <td className="mono-label">{f.email}</td>
                      <td>{f.follow_up_number}</td>
                      <td className="text-ellipsis" style={{ maxWidth: 250 }}>{f.email_subject}</td>
                      <td>{f.scheduled_at ? new Date(f.scheduled_at).toLocaleDateString() : '-'}</td>
                      <td><span className={`badge status-${f.status.toLowerCase()}`}>{f.status}</span></td>
                      <td>{f.updated_at && f.status === 'SENT' ? new Date(f.updated_at).toLocaleDateString() : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── SUMMARY TAB ── */}
      {tab === 'summary' && (
        <div>
          {summary ? (
            <div className="stats-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 16 }}>
              <div className="stat-card"><div className="stat-value">{summary.total}</div><div className="stat-label">Total Follow-ups</div></div>
              <div className="stat-card"><div className="stat-value" style={{ color: '#f59e0b' }}>{summary.pending}</div><div className="stat-label">Pending</div></div>
              <div className="stat-card"><div className="stat-value" style={{ color: '#16a34a' }}>{summary.sent}</div><div className="stat-label">Sent</div></div>
              <div className="stat-card"><div className="stat-value" style={{ color: '#6b7280' }}>{summary.skipped}</div><div className="stat-label">Skipped</div></div>
              <div className="stat-card"><div className="stat-value" style={{ color: '#ef4444' }}>{summary.failed}</div><div className="stat-label">Failed</div></div>
              <div className="stat-card"><div className="stat-value">{summary.active_rules}</div><div className="stat-label">Active Rules</div></div>
            </div>
          ) : (
            <div className="cohere-pulse" style={{ width: 32, height: 32 }}></div>
          )}

          {pending.length > 0 && (
            <div style={{ marginTop: 24 }}>
              <h3 style={{ fontSize: 15, marginBottom: 12 }}>Quick Actions</h3>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-solid" onClick={generateFollowUps} disabled={loading} style={{ height: 36, fontSize: 13 }}>
                  {loading ? 'Generating...' : 'Scan & Generate Follow-ups'}
                </button>
                <button className="btn btn-light" style={{ height: 36, fontSize: 13 }} onClick={() => handleTabChange('pending')}>
                  View Pending ({summary?.pending})
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      <style>{`
        .followups-view .tabs { display: flex; gap: 4; align-items: center; }
        .followups-view .tab { padding: 8px 16px; border: 1px solid var(--border); background: var(--card-bg); border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 500; }
        .followups-view .tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }
        .followups-view .detail-panel { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
        .followups-view .detail-field { margin-bottom: 10px; }
        .followups-view .detail-field label { display: block; font-size: 11px; font-weight: 600; color: var(--muted-slate); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
        .followups-view .detail-field span { font-size: 13px; }
        .followups-view .detail-field input { width: 100%; padding: 8px 10px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; background: var(--off-white-bg); }
        .followups-view .detail-field input[type="checkbox"] { width: auto; margin-right: 6px; }
        .followups-view .toggle-label { display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer; }
        .followups-view .empty-state { text-align: center; padding: 60px 20px; color: var(--muted-slate); }
        .followups-view .filter-bar { display: flex; align-items: center; }
        .followups-view .filter-bar select { padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; background: var(--card-bg); }
        .followups-view .data-table tr { cursor: pointer; }
        .followups-view .data-table tr.selected { background: var(--accent-light, #eef2ff); }
        .followups-view .stat-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; text-align: center; }
        .followups-view .stat-value { font-size: 32px; font-weight: 700; color: var(--matte-black); }
        .followups-view .stat-label { font-size: 12px; color: var(--muted-slate); margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
        .followups-view .email-preview { border: 1px solid var(--border); }
      `}</style>
    </div>
  );
}
