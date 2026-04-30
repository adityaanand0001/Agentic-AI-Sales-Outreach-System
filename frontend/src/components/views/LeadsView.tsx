'use client';

import { useState, useMemo } from 'react';

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
}

export default function LeadsView({
  items, page, totalPages, search, onSearchChange,
  onPrevPage, onNextPage, onIngest, ingesting, onRefresh,
}: Props) {
  const [selected, setSelected] = useState<any | null>(null);
  const [filterNew, setFilterNew] = useState<boolean | null>(null);

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
                <tr><th>Name</th><th>Company</th><th>Email</th><th>Status</th></tr>
              </thead>
              <tbody>
                {pageItems.map((lead, i) => (
                  <tr key={lead.id || i}
                    onClick={() => setSelected(lead)}
                    style={{ cursor: 'pointer', background: selected?.id === lead.id ? '#eff6ff' : undefined }}>
                    <td style={{ fontWeight: 500 }}>{lead.name || lead.first_name || '-'}</td>
                    <td>{lead.company || lead.organization || '-'}</td>
                    <td style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>{lead.email || lead.email_address || '-'}</td>
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
              <span className="mono-label">Lead Detail</span>
              <button className="toolbar-btn" onClick={() => setSelected(null)} style={{ fontSize: 10 }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
                Close
              </button>
            </div>
            <div style={{ padding: 24 }}>
              {/* Basic info */}
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
                  <div style={{ fontSize: 10, color: 'var(--muted-slate)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>Status</div>
                  {selected.is_new
                    ? <span className="badge" style={{ background: '#dbeafe', color: '#1e40af', border: 'none' }}>New / Unprocessed</span>
                    : <span className="badge" style={{ background: '#f0fdf4', color: '#166534', border: 'none' }}>Already Processed</span>
                  }
                </div>
              </div>

              {/* Context/Notes */}
              <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: 20 }}>
                <div style={{ fontSize: 10, color: 'var(--muted-slate)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>Context / Notes</div>
                <div style={{ fontSize: 13, lineHeight: 1.7, color: 'var(--near-black)', background: '#fafafa', padding: 16, borderRadius: 8, border: '1px solid var(--border-light)', whiteSpace: 'pre-wrap' }}>
                  {selected.context || selected.Context || selected.notes || selected.description || 'No context available.'}
                </div>
              </div>

              {/* Additional fields */}
              <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: 20, marginTop: 20 }}>
                <div style={{ fontSize: 10, color: 'var(--muted-slate)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>Raw Data</div>
                <div style={{ fontSize: 11, lineHeight: 1.6, fontFamily: 'JetBrains Mono, monospace', color: 'var(--muted-slate)', background: '#fafafa', padding: 16, borderRadius: 8, border: '1px solid var(--border-light)', maxHeight: 300, overflow: 'auto' }}>
                  {JSON.stringify(selected, null, 2)}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
