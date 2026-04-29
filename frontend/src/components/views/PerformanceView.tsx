'use client';

interface Props {
  metrics: any[];
  report: any | null;
  onRefresh: () => void;
}

export default function PerformanceView({ metrics, report, onRefresh }: Props) {
  return (
    <div className="view-content">
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 className="panel-title">Performance Metrics</h2>
        <button className="btn btn-ghost" onClick={onRefresh}>Refresh</button>
      </div>

      {report && (
        <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)', marginBottom: 24 }}>
          <div className="stat-card">
            <div className="stat-title">Total Processed</div>
            <div className="stat-value">{report.total_processed || 0}</div>
          </div>
          <div className="stat-card">
            <div className="stat-title">Avg Confidence</div>
            <div className="stat-value">{report.avg_confidence != null ? Math.round(report.avg_confidence * 100) + '%' : 'N/A'}</div>
          </div>
          <div className="stat-card">
            <div className="stat-title">Success Rate</div>
            <div className="stat-value">{report.success_rate != null ? Math.round(report.success_rate * 100) + '%' : 'N/A'}</div>
          </div>
          <div className="stat-card">
            <div className="stat-title">Total Sent</div>
            <div className="stat-value">{report.total_sent || report.sent || 0}</div>
          </div>
        </div>
      )}

      {metrics.length > 0 && (
        <div className="panel" style={{ marginBottom: 24 }}>
          <div className="panel-header"><h3 className="panel-title">Daily Metrics</h3></div>
          <div className="panel-body" style={{ padding: 0 }}>
            <table className="excel-table">
              <thead>
                <tr><th>Date</th><th>Processed</th><th>Sent</th><th>Failed</th><th>Avg Confidence</th></tr>
              </thead>
              <tbody>
                {metrics.map((m, i) => (
                  <tr key={i}>
                    <td>{m.date || m.day || '-'}</td>
                    <td>{m.processed || m.total || 0}</td>
                    <td>{m.sent || 0}</td>
                    <td>{m.failed || 0}</td>
                    <td>{m.avg_confidence != null ? Math.round(m.avg_confidence * 100) + '%' : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {report && report.summary && (
        <div className="panel">
          <div className="panel-header"><h3 className="panel-title">AI Analysis Summary</h3></div>
          <div className="panel-body">
            <p style={{ color: 'var(--muted-slate)', lineHeight: 1.6, fontSize: 13, whiteSpace: 'pre-wrap' }}>
              {report.summary}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
