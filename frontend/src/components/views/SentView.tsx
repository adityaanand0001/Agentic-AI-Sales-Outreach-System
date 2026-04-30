'use client';

import { useState, useMemo } from 'react';

interface Props {
  items: any[];
  onCheckReplies: () => void;
}

export default function SentView({ items, onCheckReplies }: Props) {
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<any | null>(null);
  const [threadView, setThreadView] = useState(false);
  const [page, setPage] = useState(1);
  const perPage = 15;

  const filtered = useMemo(() => {
    if (!search) return items;
    const q = search.toLowerCase();
    return items.filter(item =>
      (item.recipient || item.lead_email || '').toLowerCase().includes(q) ||
      (item.subject || item.email_subject || '').toLowerCase().includes(q) ||
      (item.company_name || '').toLowerCase().includes(q)
    );
  }, [items, search]);

  const totalPages = Math.ceil(filtered.length / perPage);
  const pageItems = filtered.slice((page - 1) * perPage, page * perPage);

  const groupedThreads = useMemo(() => {
    if (!threadView) return null;
    const groups: Record<string, any[]> = {};
    filtered.forEach(item => {
      const tid = item.thread_id || item.id;
      if (!groups[tid]) groups[tid] = [];
      groups[tid].push(item);
    });
    return groups;
  }, [filtered, threadView]);

  return (
    <div className="view-content" style={{ padding: 0, height: 'calc(100vh - 64px)', display: 'flex', flexDirection: 'column' }}>
      {/* Toolbar */}
      <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--border-light)', background: 'white', display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <h2 className="panel-title" style={{ marginRight: 12 }}>Sent History</h2>
        <input className="form-input" placeholder="Search by recipient, subject, company..."
          value={search} onChange={e => { setSearch(e.target.value); setPage(1); }}
          style={{ width: 280, padding: '8px 12px' }} />
        <div style={{ flex: 1 }} />
        <button className={`btn ${threadView ? 'btn-solid' : 'btn-ghost'}`}
          onClick={() => setThreadView(v => !v)} style={{ fontSize: 11 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
          Thread View
        </button>
        <button className="btn btn-ghost" onClick={onCheckReplies} style={{ fontSize: 11 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M22 2 11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/>
          </svg>
          Check Replies
        </button>
      </div>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* List panel */}
        <div style={{ width: selected ? 380 : '100%', borderRight: selected ? '1px solid var(--border-light)' : 'none', overflow: 'auto', background: '#fcfcfc' }}>
          {filtered.length === 0 ? (
            <div className="empty-state">
              <div className="empty-title">{search ? 'No matches' : 'No sent emails'}</div>
              <div className="empty-description">
                {search ? 'Try a different search term.' : 'Emails that have been sent will appear here.'}
              </div>
            </div>
          ) : threadView ? (
            // Thread view grouped by thread
            Object.entries(groupedThreads || {}).map(([threadId, threadItems]) => (
              <div key={threadId} style={{ borderBottom: '1px solid var(--border-light)' }}>
                <div style={{ padding: '8px 16px', background: '#f1f5f9', fontSize: 10, fontWeight: 600, color: 'var(--muted-slate)' }}>
                  Thread ({threadItems.length} messages)
                </div>
                {threadItems.map((item, idx) => (
                  <div key={item.id || idx}
                    className={`email-item ${selected?.id === item.id ? 'selected' : ''}`}
                    onClick={() => setSelected(item)}
                    style={{ paddingLeft: 24 }}>
                    <div className="email-meta">
                      <span className="email-sender">{item.recipient || item.lead_email || 'Unknown'}</span>
                      <span className="email-time">
                        {item.sent_at ? new Date(item.sent_at).toLocaleString() : item.created_at ? new Date(item.created_at).toLocaleString() : '-'}
                      </span>
                    </div>
                    <div className="email-preview-subject">{item.subject || item.email_subject || '(No subject)'}</div>
                    <div className="email-snippet">
                      {(item.email_body_preview || item.body_text || '').substring(0, 80)}
                    </div>
                  </div>
                ))}
              </div>
            ))
          ) : (
            // Flat list
            pageItems.map(item => (
              <div key={item.id}
                className={`email-item ${selected?.id === item.id ? 'selected' : ''}`}
                onClick={() => setSelected(item)}>
                <div className="email-meta">
                  <span className="email-sender">{item.recipient || item.lead_email || 'Unknown'}</span>
                  <span className="email-time">
                    {item.sent_at ? new Date(item.sent_at).toLocaleString() : item.created_at ? new Date(item.created_at).toLocaleString() : '-'}
                  </span>
                </div>
                <div className="email-preview-subject">{item.subject || item.email_subject || '(No subject)'}</div>
                <div className="email-snippet" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span className="badge">{item.status || 'sent'}</span>
                  <span style={{ color: 'var(--muted-slate)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {(item.email_body_preview || item.body_text || '').substring(0, 60)}
                  </span>
                </div>
              </div>
            ))
          )}

          {/* Pagination */}
          {!threadView && totalPages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 8, padding: 16, borderTop: '1px solid var(--border-light)', background: 'white' }}>
              <button className="btn btn-ghost" disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))}
                style={{ padding: '4px 12px', fontSize: 11 }}>Prev</button>
              <span className="mono-label" style={{ display: 'flex', alignItems: 'center' }}>
                Page {page} / {totalPages}
              </span>
              <button className="btn btn-ghost" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}
                style={{ padding: '4px 12px', fontSize: 11 }}>Next</button>
            </div>
          )}
        </div>

        {/* Detail panel */}
        {selected && (
          <div style={{ flex: 1, overflow: 'auto', background: 'white', display: 'flex', flexDirection: 'column' }}>
            <div className="detail-toolbar" style={{ justifyContent: 'space-between' }}>
              <span className="mono-label">Email Detail</span>
              <button className="toolbar-btn" onClick={() => setSelected(null)} style={{ fontSize: 10 }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
                Close
              </button>
            </div>
            <div style={{ padding: 24, maxWidth: 680 }}>
              <div style={{ marginBottom: 20 }}>
                <div style={{ fontSize: 11, color: 'var(--muted-slate)', marginBottom: 4 }}>TO</div>
                <div style={{ fontSize: 14, fontWeight: 500 }}>{selected.recipient || selected.lead_email || '-'}</div>
              </div>
              <div style={{ marginBottom: 20 }}>
                <div style={{ fontSize: 11, color: 'var(--muted-slate)', marginBottom: 4 }}>SUBJECT</div>
                <div style={{ fontSize: 16, fontWeight: 600 }}>{selected.subject || selected.email_subject || '(No subject)'}</div>
              </div>
              <div style={{ marginBottom: 20, display: 'flex', gap: 24 }}>
                <div>
                  <div style={{ fontSize: 11, color: 'var(--muted-slate)', marginBottom: 4 }}>STATUS</div>
                  <span className="badge">{selected.status || 'sent'}</span>
                </div>
                <div>
                  <div style={{ fontSize: 11, color: 'var(--muted-slate)', marginBottom: 4 }}>SENT AT</div>
                  <div style={{ fontSize: 12, fontFamily: 'JetBrains Mono, monospace' }}>
                    {selected.sent_at ? new Date(selected.sent_at).toLocaleString() : selected.created_at ? new Date(selected.created_at).toLocaleString() : '-'}
                  </div>
                </div>
                {selected.gmail_message_id && (
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--muted-slate)', marginBottom: 4 }}>GMAIL ID</div>
                    <div style={{ fontSize: 11, fontFamily: 'JetBrains Mono, monospace', color: 'var(--muted-slate)' }}>
                      {selected.gmail_message_id.substring(0, 20)}...
                    </div>
                  </div>
                )}
              </div>
              <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: 20 }}>
                <div style={{ fontSize: 11, color: 'var(--muted-slate)', marginBottom: 12 }}>BODY</div>
                <div style={{ fontSize: 13, lineHeight: 1.7, whiteSpace: 'pre-wrap', color: 'var(--near-black)', background: '#fafafa', padding: 20, borderRadius: 8, border: '1px solid var(--border-light)' }}>
                  {selected.email_body_preview || selected.body_text || '(No body content)'}
                </div>
              </div>
              {selected.thread_id && (
                <div style={{ marginTop: 16, fontSize: 11, color: 'var(--muted-slate)', fontFamily: 'JetBrains Mono, monospace' }}>
                  Thread: {selected.thread_id}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
