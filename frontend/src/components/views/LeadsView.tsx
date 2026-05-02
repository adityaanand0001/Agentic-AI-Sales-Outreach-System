'use client';

import { useState, useMemo, useEffect } from 'react';

interface Props {
  items: any[];
  page: number;
  totalPages: number;
  search: string;
  onSearchChange: (v: string) => void;
  onPrevPage: () => void;
  onNextPage: () => void;
  onIngest: () => void;
  ingesting: boolean;
  onRefresh: () => void;
  onExportCsv?: () => void;
  exporting?: boolean;
  scoring: boolean;
  onScoreLeads: () => void;
  scores: Record<string, number>;
  toast: (s: string) => void;
}

export default function LeadsView({
  items, page, totalPages, search, onSearchChange,
  onPrevPage, onNextPage, onIngest, ingesting, onRefresh,
  scoring, onScoreLeads, scores, toast,
}: Props) {
  const [selected, setSelected] = useState<any | null>(null);
  const [filterNew, setFilterNew] = useState<boolean | null>(null);
  const [notes, setNotes] = useState<any[]>([]);
  const [activity, setActivity] = useState<any[]>([]);
  const [newNote, setNewNote] = useState('');
  const [noteType, setNoteType] = useState('general');
  const [detailTab, setDetailTab] = useState<'info' | 'notes' | 'activity'>('info');

  const loadNotes = async (leadId: string) => {
    try {
      const { notes: api } = await import('@/lib/api');
      const data = await api.list(leadId);
      setNotes(data);
    } catch {}
  };

  const loadActivity = async (leadId: string) => {
    try {
      const { notes: api } = await import('@/lib/api');
      const data = await api.activity(leadId);
      setActivity(data);
    } catch {}
  };

  const addNote = async () => {
    if (!selected?.id || !newNote.trim()) return;
    try {
      const { notes: api } = await import('@/lib/api');
      await api.create(selected.id, { note_text: newNote, note_type: noteType });
      setNewNote('');
      toast('Note added');
      loadNotes(selected.id);
      loadActivity(selected.id);
    } catch (e: any) { toast(e.message); }
  };

  const deleteNote = async (noteId: string) => {
    if (!selected?.id) return;
    try {
      const { notes: api } = await import('@/lib/api');
      await api.delete(selected.id, noteId);
      toast('Note deleted');
      loadNotes(selected.id);
      loadActivity(selected.id);
    } catch (e: any) { toast(e.message); }
  };

  const handleSelect = (lead: any) => {
    setSelected(lead);
    loadNotes(lead.id);
    loadActivity(lead.id);
    setDetailTab('info');
  };

  const filtered = useMemo(() => {
    let result = items;
    if (filterNew !== null) {
      result = result.filter(item => item.is_new === filterNew);
    }
    return result;
  }, [items, filterNew]);

  const perPage = 10;
  const pageItems = filtered.slice((page - 1) * perPage, page * perPage);
  const total = Math.ceil(filtered.length / perPage) || 1;

  const totalLeads = items.length;
  const newLeads = items.filter(i => i.is_new).length;
  const processedLeads = totalLeads - newLeads;

  return (
    <div className="view-content" style={{ padding: 0, height: 'calc(100vh - 64px)', display: 'flex', flexDirection: 'column' }}>
      {/* Toolbar */}
      <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--border-light)', background: 'white', display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <h2 className="panel-title" style={{ marginRight: 12 }}>Lead Management</h2>
        <input className="form-input" placeholder="Search leads by name, company, email..."
          value={search} onChange={e => onSearchChange(e.target.value)}
          style={{ width: 260, padding: '8px 12px' }} />
        <div style={{ display: 'flex', gap: 4 }}>
          {[null, true, false].map(v => (
            <button key={String(v)}
              className={`btn ${filterNew === v ? 'btn-solid' : 'btn-ghost'}`}
              onClick={() => { setFilterNew(v); onSearchChange(''); }}
              style={{ fontSize: 11, padding: '4px 10px' }}>
              {v === null ? 'All' : v ? 'New' : 'Processed'}
            </button>
          ))}
        </div>
        <div style={{ flex: 1 }} />
        <button className="btn btn-ghost" onClick={onRefresh} style={{ fontSize: 11 }} disabled={ingesting}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
          Refresh
        </button>
        <button className="btn btn-solid" onClick={onIngest} disabled={ingesting} style={{ fontSize: 11 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          {ingesting ? 'Ingesting...' : 'Ingest Leads'}
        </button>
        <button className="btn" onClick={onScoreLeads} disabled={scoring}
          style={{ fontSize: 11, background: scoring ? '#dbeafe' : '#2563eb', color: scoring ? '#1e40af' : 'white', border: 'none', borderRadius: 6, padding: '8px 16px', cursor: scoring ? 'default' : 'pointer' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 4 }}>
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
          </svg>
          {scoring ? 'Scoring...' : 'Score Leads'}
        </button>
      </div>

      {/* Stats bar */}
      <div style={{ display: 'flex', gap: 16, padding: '12px 24px', background: '#f8fafc', borderBottom: '1px solid var(--border-light)' }}>
        <div><span className="mono-label" style={{ color: 'var(--muted-slate)' }}>Total: </span><strong>{totalLeads}</strong></div>
        <div><span className="mono-label" style={{ color: 'var(--muted-slate)' }}>New: </span><strong style={{ color: '#2563eb' }}>{newLeads}</strong></div>
        <div><span className="mono-label" style={{ color: 'var(--muted-slate)' }}>Processed: </span><strong style={{ color: '#166534' }}>{processedLeads}</strong></div>
      </div>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Table panel */}
        <div style={{ flex: selected ? '0 0 45%' : 1, overflow: 'auto', borderRight: selected ? '1px solid var(--border-light)' : 'none' }}>
          {filtered.length === 0 ? (
            <div className="empty-state">
              <div className="empty-title">{search || filterNew !== null ? 'No matching leads' : 'No leads found'}</div>
              <div className="empty-description">
                {search || filterNew !== null ? 'Try different filters.' : 'Ingest leads from your data source to get started.'}
              </div>
            </div>
          ) : (
            <table className="excel-table">
              <thead>
                <tr><th>Name</th><th>Company</th><th>Email</th><th>Score</th><th>Status</th></tr>
              </thead>
              <tbody>
                {pageItems.map((lead, i) => (
                  <tr key={lead.id || i}
                    onClick={() => handleSelect(lead)}
                    style={{ cursor: 'pointer', background: selected?.id === lead.id ? '#eff6ff' : undefined }}>
                    <td style={{ fontWeight: 500 }}>{lead.name || lead.first_name || '-'}</td>
                    <td>{lead.company || lead.organization || '-'}</td>
                    <td style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>{lead.email || lead.email_address || '-'}</td>
                    <td>
                      {(() => {
                        const s = scores[lead.id];
                        if (s === undefined) return <span style={{ color: 'var(--muted-slate)', fontSize: 11 }}>—</span>;
                        const color = s >= 70 ? '#059669' : s >= 40 ? '#d97706' : '#dc2626';
                        const bg = s >= 70 ? '#ecfdf5' : s >= 40 ? '#fffbeb' : '#fef2f2';
                        return <span style={{ fontWeight: 600, fontSize: 13, color, background: bg, padding: '2px 8px', borderRadius: 10 }}>{s}</span>;
                      })()}
                    </td>
                    <td>
                      {lead.is_new
                        ? <span className="badge" style={{ background: '#dbeafe', color: '#1e40af', border: 'none' }}>New</span>
                        : <span className="badge" style={{ background: '#f0fdf4', color: '#166534', border: 'none' }}>Processed</span>
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {total > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 8, padding: 12, borderTop: '1px solid var(--border-light)', background: 'white' }}>
              <button className="btn btn-ghost" disabled={page <= 1} onClick={onPrevPage}
                style={{ padding: '4px 12px', fontSize: 11 }}>Prev</button>
              <span className="mono-label" style={{ display: 'flex', alignItems: 'center' }}>Page {page} / {total}</span>
              <button className="btn btn-ghost" disabled={page >= total} onClick={onNextPage}
                style={{ padding: '4px 12px', fontSize: 11 }}>Next</button>
            </div>
          )}
        </div>

        {/* Detail panel */}
        {selected && (
          <div style={{ flex: 1, overflow: 'auto', background: 'white' }}>
            <div className="detail-toolbar" style={{ justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', gap: 4 }}>
                {(['info', 'notes', 'activity'] as const).map(t => (
                  <button key={t} className={`btn ${detailTab === t ? 'btn-solid' : 'btn-ghost'}`}
                    onClick={() => setDetailTab(t)} style={{ fontSize: 11, padding: '3px 10px', textTransform: 'capitalize' }}>
                    {t}{t === 'notes' ? ` (${notes.length})` : ''}{t === 'activity' ? ` (${activity.length})` : ''}
                  </button>
                ))}
              </div>
              <button className="toolbar-btn" onClick={() => setSelected(null)} style={{ fontSize: 10 }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
                Close
              </button>
            </div>

            {detailTab === 'info' && (
              <div style={{ padding: 24 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24 }}>
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--muted-slate)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>Name</div>
                    <div style={{ fontSize: 15, fontWeight: 600 }}>{selected.name || selected.first_name || '-'}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--muted-slate)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>Company</div>
                    <div style={{ fontSize: 15, fontWeight: 500 }}>{selected.company || selected.organization || '-'}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--muted-slate)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>Email</div>
                    <div style={{ fontSize: 13, fontFamily: 'JetBrains Mono, monospace' }}>{selected.email || selected.email_address || '-'}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--muted-slate)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>AI Score</div>
                    {(() => {
                      const s = scores[selected.id];
                      if (s === undefined) return <span style={{ color: 'var(--muted-slate)', fontSize: 13 }}>Not scored yet</span>;
                      const color = s >= 70 ? '#059669' : s >= 40 ? '#d97706' : '#dc2626';
                      const label = s >= 70 ? 'High' : s >= 40 ? 'Medium' : 'Low';
                      return <span style={{ fontWeight: 600, fontSize: 18, color }}>{s}<span style={{ fontSize: 11, fontWeight: 400, marginLeft: 6 }}>{label} priority</span></span>;
                    })()}
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--muted-slate)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>Status</div>
                    {selected.is_new
                      ? <span className="badge" style={{ background: '#dbeafe', color: '#1e40af', border: 'none' }}>New / Unprocessed</span>
                      : <span className="badge" style={{ background: '#f0fdf4', color: '#166534', border: 'none' }}>Already Processed</span>
                    }
                  </div>
                </div>
                <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: 20 }}>
                  <div style={{ fontSize: 10, color: 'var(--muted-slate)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>Context / Notes</div>
                  <div style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--near-black)', background: '#fafafa', padding: 16, borderRadius: 8, border: '1px solid var(--border-light)', whiteSpace: 'pre-wrap' }}>
                    {selected.context || selected.Context || selected.notes || selected.description || 'No context available.'}
                  </div>
                </div>
                <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: 20, marginTop: 20 }}>
                  <div style={{ fontSize: 10, color: 'var(--muted-slate)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>Raw Data</div>
                  <div style={{ fontSize: 11, lineHeight: 1.6, fontFamily: 'JetBrains Mono, monospace', color: 'var(--muted-slate)', background: '#fafafa', padding: 16, borderRadius: 8, border: '1px solid var(--border-light)', maxHeight: 300, overflow: 'auto' }}>
                    {JSON.stringify(selected, null, 2)}
                  </div>
                </div>
              </div>
            )}

            {detailTab === 'notes' && (
              <div style={{ padding: 24 }}>
                <div style={{ marginBottom: 20, padding: 16, background: '#f8fafc', borderRadius: 8, border: '1px solid var(--border-light)' }}>
                  <textarea className="form-input" value={newNote} onChange={e => setNewNote(e.target.value)}
                    placeholder="Add a note about this lead..." rows={3} style={{ width: '100%', resize: 'vertical', marginBottom: 8 }} />
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <select value={noteType} onChange={e => setNoteType(e.target.value)}
                      style={{ fontSize: 11, padding: '4px 8px', borderRadius: 6, border: '1px solid var(--border-light)', background: 'white' }}>
                      {['general', 'call', 'meeting', 'follow_up', 'research', 'other'].map(t => (
                        <option key={t} value={t}>{t.replace('_', ' ')}</option>
                      ))}
                    </select>
                    <button className="btn btn-solid" onClick={addNote} disabled={!newNote.trim()} style={{ fontSize: 11 }}>Add Note</button>
                  </div>
                </div>
                {notes.length === 0 ? (
                  <div style={{ textAlign: 'center', color: 'var(--muted-slate)', padding: 32 }}>No notes yet. Add your first note above.</div>
                ) : (
                  notes.map(n => (
                    <div key={n.id} style={{ padding: '12px 0', borderBottom: '1px solid var(--border-light)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
                            <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 4, background: '#e2e8f0', color: '#475569', textTransform: 'capitalize' }}>{n.note_type}</span>
                            <span style={{ fontSize: 11, color: 'var(--muted-slate)' }}>{new Date(n.created_at).toLocaleString()}</span>
                          </div>
                          <div style={{ fontSize: 13, lineHeight: 1.5 }}>{n.note_text}</div>
                        </div>
                        <button onClick={() => deleteNote(n.id)} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: 11, padding: 4 }}>Delete</button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {detailTab === 'activity' && (
              <div style={{ padding: 24 }}>
                {activity.length === 0 ? (
                  <div style={{ textAlign: 'center', color: 'var(--muted-slate)', padding: 32 }}>No activity recorded for this lead yet.</div>
                ) : (
                  <div style={{ position: 'relative', paddingLeft: 24 }}>
                    <div style={{ position: 'absolute', left: 7, top: 4, bottom: 4, width: 2, background: '#e2e8f0' }} />
                    {activity.map((a, i) => {
                      const typeColors: Record<string, string> = { tracker: '#2563eb', note: '#059669', compliance: '#d97706' };
                      const typeLabels: Record<string, string> = { tracker: 'Email', note: 'Note', compliance: 'Compliance' };
                      return (
                        <div key={i} style={{ position: 'relative', marginBottom: 16, paddingLeft: 20 }}>
                          <div style={{
                            position: 'absolute', left: -20, top: 4, width: 10, height: 10, borderRadius: '50%',
                            background: typeColors[a.activity_type] || '#6b7280', border: '2px solid white',
                          }} />
                          <div style={{ fontSize: 10, color: 'var(--muted-slate)', marginBottom: 2 }}>
                            <span style={{ fontWeight: 600, color: typeColors[a.activity_type] || '#6b7280' }}>{typeLabels[a.activity_type] || a.activity_type}</span>
                            {' · '}{new Date(a.timestamp).toLocaleString()}
                          </div>
                          <div style={{ fontSize: 13 }}>{a.description}</div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
