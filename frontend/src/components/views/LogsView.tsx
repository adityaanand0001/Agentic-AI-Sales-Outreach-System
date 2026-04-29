'use client';

interface Props {
  items: any[];
  search: string;
  onSearchChange: (v: string) => void;
  onRefresh: () => void;
}

export default function LogsView({ items, search, onSearchChange, onRefresh }: Props) {
  const filtered = search
    ? items.filter(item =>
        (item.message || item.event || '').toLowerCase().includes(search.toLowerCase()) ||
        (item.level || item.event_type || '').toLowerCase().includes(search.toLowerCase()))
    : items;

  return (
    <div className="view-content">
      <div style={{ marginBottom: 20, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
        <h2 className="panel-title">System Logs</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input className="form-input" placeholder="Filter logs..." value={search}
            onChange={e => onSearchChange(e.target.value)} style={{ width: 200 }} />
          <button className="btn btn-ghost" onClick={onRefresh}>Refresh</button>
        </div>
      </div>
      {filtered.length === 0 ? (
        <div className="empty-state">
          <div className="empty-title">{search ? 'No matching logs' : 'No logs'}</div>
          <div className="empty-description">
            {search ? 'Try a different search term.' : 'Agent activity logs will appear here.'}
          </div>
        </div>
      ) : (
        <div className="panel">
          <div className="panel-body" style={{ padding: 0, maxHeight: 'calc(100vh - 240px)', overflow: 'auto' }}>
            <table className="excel-table">
              <thead>
                <tr><th>Time</th><th>Level</th><th>Message</th><th>Tracker</th></tr>
              </thead>
              <tbody>
                {filtered.map((log, i) => (
                  <tr key={log.id || i}>
                    <td style={{ whiteSpace: 'nowrap', fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>
                      {log.timestamp ? new Date(log.timestamp).toLocaleString() : '-'}
                    </td>
                    <td><span className="badge">{log.level || log.event_type || 'info'}</span></td>
                    <td style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, whiteSpace: 'pre-wrap' }}>
                      {log.message || log.event || '-'}
                    </td>
                    <td style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>
                      {log.tracker_id ? log.tracker_id.substring(0, 12) + '...' : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
