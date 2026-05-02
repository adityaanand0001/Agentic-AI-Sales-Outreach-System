'use client';

import { useState, useEffect } from 'react';

interface Props {
  toast: (s: string) => void;
}

export default function CampaignsView({ toast }: Props) {
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [selected, setSelected] = useState<any | null>(null);
  const [form, setForm] = useState({ name: '', description: '', target_audience: '' });
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  const load = async () => {
    try {
      const { campaigns: api } = await import('@/lib/api');
      const data = await api.list();
      setCampaigns(data);
    } catch (e: any) { toast(e.message); }
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    try {
      const { campaigns: api } = await import('@/lib/api');
      await api.create(form);
      toast('Campaign created');
      setForm({ name: '', description: '', target_audience: '' });
      setShowForm(false);
      load();
    } catch (e: any) { toast(e.message); }
  };

  const handleUpdate = async () => {
    if (!editingId) return;
    try {
      const { campaigns: api } = await import('@/lib/api');
      await api.update(editingId, form);
      toast('Campaign updated');
      setEditingId(null);
      setShowForm(false);
      setForm({ name: '', description: '', target_audience: '' });
      load();
    } catch (e: any) { toast(e.message); }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this campaign? Emails will be unlinked but not deleted.')) return;
    try {
      const { campaigns: api } = await import('@/lib/api');
      await api.delete(id);
      toast('Campaign deleted');
      if (selected?.id === id) setSelected(null);
      load();
    } catch (e: any) { toast(e.message); }
  };

  const startEdit = (c: any) => {
    setEditingId(c.id);
    setForm({ name: c.name, description: c.description || '', target_audience: c.target_audience || '' });
    setShowForm(true);
  };

  const selectCampaign = async (id: string) => {
    try {
      const { campaigns: api } = await import('@/lib/api');
      const data = await api.get(id);
      setSelected(data);
    } catch (e: any) { toast(e.message); }
  };

  const statusColors: Record<string, string> = {
    ACTIVE: '#059669', PAUSED: '#d97706', COMPLETED: '#2563eb', ARCHIVED: '#6b7280',
  };

  return (
    <div className="view-content" style={{ padding: 0, height: 'calc(100vh - 64px)', display: 'flex', flexDirection: 'column' }}>
      {/* Toolbar */}
      <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--border-light)', background: 'white', display: 'flex', gap: 12, alignItems: 'center' }}>
        <h2 className="panel-title">Campaigns</h2>
        <div style={{ flex: 1 }} />
        <button className="btn btn-ghost" onClick={load} style={{ fontSize: 11 }}>Refresh</button>
        <button className="btn btn-solid" onClick={() => { setEditingId(null); setForm({ name: '', description: '', target_audience: '' }); setShowForm(true); }} style={{ fontSize: 11 }}>
          + New Campaign
        </button>
      </div>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Campaign list */}
        <div style={{ flex: selected || showForm ? '0 0 40%' : 1, overflow: 'auto', borderRight: (selected || showForm) ? '1px solid var(--border-light)' : 'none' }}>
          {campaigns.length === 0 ? (
            <div className="empty-state">
              <div className="empty-title">No campaigns yet</div>
              <div className="empty-description">Create a campaign to organize your outreach efforts.</div>
            </div>
          ) : (
            campaigns.map(c => (
              <div key={c.id}
                onClick={() => selectCampaign(c.id)}
                style={{
                  padding: '16px 24px', cursor: 'pointer', borderBottom: '1px solid var(--border-light)',
                  background: selected?.id === c.id ? '#f0f9ff' : 'white',
                  borderLeft: selected?.id === c.id ? '3px solid #2563eb' : '3px solid transparent',
                }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{c.name}</span>
                  <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 10, background: statusColors[c.status] + '18', color: statusColors[c.status], fontWeight: 600 }}>
                    {c.status}
                  </span>
                </div>
                {c.description && <div style={{ fontSize: 12, color: 'var(--muted-slate)', marginBottom: 8 }}>{c.description}</div>}
                <div style={{ display: 'flex', gap: 16, fontSize: 11, color: 'var(--muted-slate)' }}>
                  <span>{c.sent_count ?? 0} sent</span>
                  <span>{c.reply_count ?? 0} replies</span>
                  <span>{c.bounce_count ?? 0} bounced</span>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Campaign detail */}
        {selected && !showForm && (
          <div style={{ flex: 1, overflow: 'auto', background: 'white' }}>
            <div className="detail-toolbar" style={{ justifyContent: 'space-between' }}>
              <span className="mono-label">Campaign Detail</span>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="toolbar-btn" onClick={() => startEdit(selected)} style={{ fontSize: 10 }}>Edit</button>
                <button className="toolbar-btn" onClick={() => handleDelete(selected.id)} style={{ fontSize: 10, color: '#ef4444' }}>Delete</button>
                <button className="toolbar-btn" onClick={() => setSelected(null)} style={{ fontSize: 10 }}>Close</button>
              </div>
            </div>
            <div style={{ padding: 24 }}>
              <h3 style={{ fontSize: 20, marginBottom: 8 }}>{selected.name}</h3>
              {selected.description && <p style={{ color: 'var(--muted-slate)', marginBottom: 24 }}>{selected.description}</p>}

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 32 }}>
                {[
                  { label: 'Sent', value: selected.sent_count ?? 0, color: '#059669' },
                  { label: 'Replies', value: selected.reply_count ?? 0, color: '#2563eb' },
                  { label: 'Bounced', value: selected.bounce_count ?? 0, color: '#dc2626' },
                  { label: 'Total Tracked', value: selected.total_leads ?? 0, color: '#6b7280' },
                ].map(s => (
                  <div key={s.label} style={{ textAlign: 'center', padding: 16, background: '#f8fafc', borderRadius: 8, border: '1px solid var(--border-light)' }}>
                    <div style={{ fontSize: 24, fontWeight: 700, color: s.color }}>{s.value}</div>
                    <div style={{ fontSize: 11, color: 'var(--muted-slate)', marginTop: 4 }}>{s.label}</div>
                  </div>
                ))}
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24 }}>
                <div>
                  <div style={{ fontSize: 10, color: 'var(--muted-slate)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>Status</div>
                  <span style={{ fontSize: 13, padding: '3px 12px', borderRadius: 6, background: statusColors[selected.status] + '18', color: statusColors[selected.status], fontWeight: 600 }}>
                    {selected.status}
                  </span>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: 'var(--muted-slate)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>Target Audience</div>
                  <div style={{ fontSize: 13 }}>{selected.target_audience || '-'}</div>
                </div>
                {selected.start_date && (
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--muted-slate)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>Start Date</div>
                    <div style={{ fontSize: 13 }}>{new Date(selected.start_date).toLocaleDateString()}</div>
                  </div>
                )}
                {selected.end_date && (
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--muted-slate)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>End Date</div>
                    <div style={{ fontSize: 13 }}>{new Date(selected.end_date).toLocaleDateString()}</div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Create/Edit form */}
        {showForm && (
          <div style={{ flex: 1, overflow: 'auto', background: 'white' }}>
            <div className="detail-toolbar" style={{ justifyContent: 'space-between' }}>
              <span className="mono-label">{editingId ? 'Edit Campaign' : 'New Campaign'}</span>
              <button className="toolbar-btn" onClick={() => { setShowForm(false); setEditingId(null); }} style={{ fontSize: 10 }}>Cancel</button>
            </div>
            <div style={{ padding: 24, maxWidth: 500 }}>
              <div style={{ marginBottom: 16 }}>
                <label style={{ fontSize: 11, fontWeight: 600, marginBottom: 4, display: 'block' }}>Name *</label>
                <input className="form-input" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="e.g. Q2 Enterprise Outreach" style={{ width: '100%' }} />
              </div>
              <div style={{ marginBottom: 16 }}>
                <label style={{ fontSize: 11, fontWeight: 600, marginBottom: 4, display: 'block' }}>Description</label>
                <textarea className="form-input" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                  placeholder="What is this campaign about?" rows={3} style={{ width: '100%', resize: 'vertical' }} />
              </div>
              <div style={{ marginBottom: 24 }}>
                <label style={{ fontSize: 11, fontWeight: 600, marginBottom: 4, display: 'block' }}>Target Audience</label>
                <input className="form-input" value={form.target_audience} onChange={e => setForm(f => ({ ...f, target_audience: e.target.value }))}
                  placeholder="e.g. SaaS founders in India" style={{ width: '100%' }} />
              </div>
              <button className="btn btn-solid" onClick={editingId ? handleUpdate : handleCreate} disabled={!form.name.trim()}>
                {editingId ? 'Save Changes' : 'Create Campaign'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
