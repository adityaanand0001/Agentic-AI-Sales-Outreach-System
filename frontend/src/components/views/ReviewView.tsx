'use client';
interface Props {
  items: any[]; selectedId: string | null; onSelect: (item: any) => void;
  bulkIds: Set<string>; onToggleBulk: (id: string) => void;
  onBulkApprove: () => void; onBulkReject: () => void; onClearBulk: () => void;
  selectedDraft: any | null; editorSubject: string; editorBody: string;
  onSubjectChange: (v: string) => void; onBodyChange: (v: string) => void;
  onApprove: () => void; onReject: () => void; onRefresh: () => void;
}
const cc = (c: number) => 'confidence-pill ' + (c >= 0.7 ? 'conf-high' : c >= 0.4 ? 'conf-medium' : 'conf-low');
const FS = { flex: 1 };
export default function ReviewView({items, selectedId, onSelect, bulkIds, onToggleBulk, onBulkApprove, onBulkReject, onClearBulk, selectedDraft, editorSubject, editorBody, onSubjectChange, onBodyChange, onApprove, onReject, onRefresh}: Props) { return (
    <div className="review-layout">
      <div className="review-sidebar">
        <div className="detail-toolbar" style={{ justifyContent: 'space-between', padding: '0 16px' }}>
          <span className="mono-label">Pending ({items.length})</span>
          <button className="toolbar-btn" onClick={onRefresh}>Refresh</button>
        </div>
        <div className="list-content">
          {items.length === 0 ? (
            <div className="empty-state"><div className="empty-title">All Clear</div><div className="empty-description">No pending emails to review.</div></div>
          ) : items.map(item => (
            <div key={item.id} className={`email-item ${selectedId === item.id ? 'selected' : ''}`}
              onClick={() => onSelect(item)} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
              <input type="checkbox" checked={bulkIds.has(item.id)} onChange={() => onToggleBulk(item.id)}
                onClick={e => e.stopPropagation()} style={{ marginTop: 4 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="email-meta">
                  <span className="email-sender">{item.recipient || item.lead_email || 'Unknown'}</span>
                  <span className="email-time">{item.created_at ? new Date(item.created_at).toLocaleDateString() : ''}</span>
                </div>
                <div className="email-preview-subject">{item.subject || '(No subject)'}</div>
                <div className="email-snippet">{(item.body_text || item.generated_body || '').substring(0, 60)}</div>
                {item.ai_confidence != null && <div style={{ marginTop: 4 }}><span className={cc(item.ai_confidence)}>{Math.round(item.ai_confidence * 100)}%</span></div>}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="review-main">
        <div className="detail-toolbar">
          <button className="toolbar-btn primary" disabled={!selectedDraft} onClick={onApprove}>Approve</button>
          <button className="toolbar-btn" disabled={!selectedDraft} onClick={onReject}>Reject</button>
          <div style={FS} /><span className="mono-label" style={{ fontSize: 10 }}>Esc to close</span>
        </div>
        {selectedDraft ? (
          <div style={{ padding: 24, overflow: 'auto', flex: 1 }}>
            <div className="form-group" style={{ marginBottom: 12 }}>
              <label className="form-label">To</label>
              <input className="form-input" value={selectedDraft.recipient || selectedDraft.lead_email || ''} readOnly />
            </div>
            <div className="form-group" style={{ marginBottom: 12 }}>
              <label className="form-label">Subject</label>
              <input className="form-input" value={editorSubject} onChange={e => onSubjectChange(e.target.value)} />
            </div>
            <div className="form-group" style={{ marginBottom: 12 }}>
              <label className="form-label">Body</label>
              <textarea className="form-input form-textarea" value={editorBody} onChange={e => onBodyChange(e.target.value)} style={{ minHeight: 160 }} />
            </div>
            {selectedDraft.ai_confidence != null && <div style={{ marginBottom: 12 }}><span className={cc(selectedDraft.ai_confidence)}>AI: {Math.round(selectedDraft.ai_confidence * 100)}%</span></div>}
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-solid" onClick={onApprove}>Approve & Send</button>
              <button className="btn btn-ghost" onClick={onReject}>Reject</button>
            </div>
          </div>
        ) : (
          <div className="empty-state"><div className="empty-title">Select an email</div><div className="empty-description">Choose an email to review, approve, or reject.</div></div>
        )}
      </div>
      {bulkIds.size > 0 && (
        <div id="bulk-bar" className="visible">
          <span className="mono-label" style={{ color: 'white' }}>{bulkIds.size} selected</span>
          <button className="bulk-btn primary" onClick={onBulkApprove}>Approve All</button>
          <button className="bulk-btn danger" onClick={onBulkReject}>Reject All</button>
          <button className="bulk-btn" onClick={onClearBulk}>Clear</button>
        </div>
      )}
    </div>
  );
}
