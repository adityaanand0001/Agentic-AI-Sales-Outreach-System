'use client';

interface Props {
  items: any[];
  onCheckReplies: () => void;
}

export default function SentView({ items, onCheckReplies }: Props) {
  return (
    <div className="view-content">
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 className="panel-title">Sent History</h2>
        <button className="btn btn-ghost" onClick={onCheckReplies}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          Check Replies
        </button>
      </div>
      {items.length === 0 ? (
        <div className="empty-state">
          <div className="empty-title">No sent emails</div>
          <div className="empty-description">Emails that have been sent will appear here.</div>
        </div>
      ) : (
        <table className="excel-table">
          <thead>
            <tr><th>Recipient</th><th>Subject</th><th>Sent At</th><th>Status</th></tr>
          </thead>
          <tbody>
            {items.map(item => (
              <tr key={item.id}>
                <td>{item.recipient || item.lead_email || '-'}</td>
                <td>{item.subject || '(No subject)'}</td>
                <td>{item.sent_at ? new Date(item.sent_at).toLocaleString() : item.created_at ? new Date(item.created_at).toLocaleString() : '-'}</td>
                <td><span className="badge">{item.status || 'sent'}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
