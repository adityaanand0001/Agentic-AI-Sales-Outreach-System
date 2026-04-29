'use client';

interface Props {
  summary: any;
  items: any[];
  onRefresh: () => void;
}

export default function ComplianceView({ summary, items, onRefresh }: Props) {
  return (
    <div className="view-content">
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 className="panel-title">Compliance Tracker</h2>
        <button className="btn btn-ghost" onClick={onRefresh}>Refresh</button>
      </div>

      {summary && (
        <div className="compliance-stats">
          <div className="stat-card">
            <div className="stat-title">Total Checks</div>
            <div className="stat-value">{summary.total_checks || 0}</div>
          </div>
          <div className="stat-card">
            <div className="stat-title">Passed</div>
            <div className="stat-value" style={{ color: '#166534' }}>{summary.passed || 0}</div>
          </div>
          <div className="stat-card">
            <div className="stat-title">Warnings</div>
            <div className="stat-value" style={{ color: '#854d0e' }}>{summary.warnings || 0}</div>
          </div>
          <div className="stat-card">
            <div className="stat-title">Failures</div>
            <div className="stat-value" style={{ color: '#991b1b' }}>{summary.failures || 0}</div>
          </div>
        </div>
      )}

      {items.length > 0 ? (
        <div className="panel">
          <div className="panel-header"><h3 className="panel-title">Compliance Events</h3></div>
          <div className="panel-body" style={{ padding: 0 }}>
            <table className="excel-table">
              <thead>
                <tr><th>Email</th><th>Check</th><th>Status</th><th>Result</th><th>Date</th></tr>
              </thead>
              <tbody>
                {items.map((c, i) => (
                  <tr key={c.id || i}>
                    <td>{c.email || c.recipient || '-'}</td>
                    <td>{c.check_type || c.check || '-'}</td>
                    <td>
                      <span className="badge" style={{
                        background: c.status === 'pass' ? '#dcfce7' : c.status === 'warn' ? '#fef9c3' : '#fee2e2',
                        color: c.status === 'pass' ? '#166534' : c.status === 'warn' ? '#854d0e' : '#991b1b',
                        border: 'none',
                      }}>{c.status || 'unknown'}</span>
                    </td>
                    <td>{c.result || c.details || '-'}</td>
                    <td>{c.checked_at || c.created_at ? new Date(c.checked_at || c.created_at).toLocaleString() : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="empty-state">
          <div className="empty-title">No compliance data</div>
          <div className="empty-description">Compliance checks will appear here once available.</div>
        </div>
      )}
    </div>
  );
}
