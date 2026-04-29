'use client';

interface Props {
  items: any[];
}

export default function BatchesView({ items }: Props) {
  return (
    <div className="view-content">
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 className="panel-title">Batch History</h2>
      </div>
      {items.length === 0 ? (
        <div className="empty-state">
          <div className="empty-title">No batches</div>
          <div className="empty-description">Run a batch and it will appear here.</div>
        </div>
      ) : (
        <table className="excel-table">
          <thead>
            <tr><th>Batch ID</th><th>Status</th><th>Total</th><th>Sent</th><th>Failed</th><th>Created</th></tr>
          </thead>
          <tbody>
            {items.map(b => (
              <tr key={b.id || b.batch_id}>
                <td style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>
                  {(b.id || b.batch_id || '').substring(0, 16)}...
                </td>
                <td><span className="badge">{b.status || 'unknown'}</span></td>
                <td>{b.total || b.total_count || 0}</td>
                <td>{b.sent || b.sent_count || 0}</td>
                <td>{b.failed || b.failed_count || 0}</td>
                <td>{b.created_at ? new Date(b.created_at).toLocaleString() : '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
