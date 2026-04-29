'use client';

interface Props {
  stats: { total: number; pending: number; sent: number; failed: number };
  agentRunning: boolean;
  onInvoke: () => void;
  leads: any[];
  leadsPage: number;
  onPrevPage: () => void;
  onNextPage: () => void;
}

export default function DashboardView({ stats, agentRunning, onInvoke, leads, leadsPage, onPrevPage, onNextPage }: Props) {
  const perPage = 5;
  const totalPages = Math.ceil(leads.length / perPage) || 1;
  const pageLeads = leads.slice((leadsPage - 1) * perPage, leadsPage * perPage);
  const cards = [
    { t: 'Total Processed', v: stats.total },
    { t: 'Successfully Sent', v: stats.sent },
    { t: 'Needs Approval', v: stats.pending },
    { t: 'Failed / Rejected', v: stats.failed },
  ];
  const dot = (on: boolean) => ({ width: 10, height: 10, borderRadius: '50%' as const, background: on ? '#22c55e' : '#ef4444' });

  return (
    <div className="view-content">
      <div className="stats-grid">
        {cards.map(c => <div key={c.t} className="stat-card"><div className="stat-title">{c.t}</div><div className="stat-value">{c.v}</div></div>)}
      </div>
      <div className="panel" style={{ marginBottom: 24 }}>
        <div className="panel-header"><h3 className="panel-title">System Control</h3></div>
        <div className="panel-body" style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={dot(agentRunning)} /><span className="mono-label">{agentRunning ? 'Agent Running' : 'Agent Idle'}</span>
          </div>
          <button className="btn btn-solid" onClick={onInvoke}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            Invoke Agent
          </button>
        </div>
      </div>
      <div className="panel">
        <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 className="panel-title">Source Database Preview</h3>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span className="mono-label" style={{ fontSize: 10 }}>Page {leadsPage} / {totalPages}</span>
            <button className="btn btn-ghost" disabled={leadsPage <= 1} onClick={onPrevPage} style={{ padding: '4px 8px' }}>Prev</button>
            <button className="btn btn-ghost" disabled={leadsPage >= totalPages} onClick={onNextPage} style={{ padding: '4px 8px' }}>Next</button>
          </div>
        </div>
        <div className="panel-body" style={{ padding: 0 }}>
          <table className="excel-table">
            <thead><tr><th>#</th><th>Name</th><th>Company</th><th>Email</th></tr></thead>
            <tbody>
              {pageLeads.length === 0
                ? <tr><td colSpan={4} style={{ textAlign: 'center', padding: 24, color: 'var(--muted-slate)' }}>No leads found.</td></tr>
                : pageLeads.map((lead, i) => (
                    <tr key={lead.id || i}>
                      <td>{(leadsPage - 1) * perPage + i + 1}</td>
                      <td>{lead.name || lead.first_name || '-'}</td>
                      <td>{lead.company || '-'}</td>
                      <td style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>{lead.email || lead.email_address || '-'}</td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
