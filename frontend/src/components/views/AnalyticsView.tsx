'use client';

import { useState, useEffect, useCallback } from 'react';
import * as api from '@/lib/api';

interface Props {
  toast: (msg: string) => void;
}

export default function AnalyticsView({ toast }: Props) {
  const [report, setReport] = useState<any>(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.analytics.report(days);
      setReport(r);
    } catch (e: any) {
      toast(e.message);
    }
    setLoading(false);
  }, [days, toast]);

  useEffect(() => { load(); }, [load]);

  const exportCsv = () => {
    if (!report) return;
    setExporting(true);
    try {
      const rows = [['Metric', 'Value']];
      const s = report.summary || {};
      Object.entries(s).forEach(([k, v]) => rows.push([k.replace(/_/g, ' '), String(v)]));
      rows.push([]);
      rows.push(['Date', 'Sent', 'Failed', 'Pending', 'Rejected']);
      (report.volume_over_time || []).forEach((d: any) =>
        rows.push([d.date, String(d.sent), String(d.failed), String(d.pending), String(d.rejected)])
      );
      const csv = rows.map(r => r.join(',')).join('\n');
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `analytics_report_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast('Report exported as CSV');
    } catch { toast('Export failed'); }
    setExporting(false);
  };

  if (loading && !report) {
    return <div className="view-content"><div className="cohere-pulse" style={{ width: 32, height: 32, margin: '40px auto' }}></div></div>;
  }

  const s = report?.summary || {};

  return (
    <div className="view-content">
      {/* Controls */}
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <h2 className="panel-title" style={{ margin: 0 }}>Email Analytics & Insights</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select
            className="input"
            value={days}
            onChange={e => setDays(Number(e.target.value))}
            style={{ width: 120, padding: '6px 10px', fontSize: 12 }}
          >
            <option value={7}>Last 7 days</option>
            <option value={14}>Last 14 days</option>
            <option value={30}>Last 30 days</option>
            <option value={60}>Last 60 days</option>
            <option value={90}>Last 90 days</option>
          </select>
          <button className="btn btn-ghost" onClick={load} disabled={loading}>{loading ? 'Loading...' : 'Refresh'}</button>
          <button className="btn btn-light" onClick={exportCsv} disabled={exporting}>{exporting ? 'Exporting...' : 'Export CSV'}</button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', marginBottom: 24 }}>
        <div className="stat-card"><div className="stat-title">Total Emails</div><div className="stat-value">{s.total_emails || 0}</div></div>
        <div className="stat-card"><div className="stat-title">Sent</div><div className="stat-value" style={{ color: 'var(--green)' }}>{s.total_sent || 0}</div></div>
        <div className="stat-card"><div className="stat-title">Failed</div><div className="stat-value" style={{ color: '#ef4444' }}>{s.total_failed || 0}</div></div>
        <div className="stat-card"><div className="stat-title">Pending</div><div className="stat-value" style={{ color: 'var(--accent)' }}>{s.total_pending || 0}</div></div>
        <div className="stat-card"><div className="stat-title">Success Rate</div><div className="stat-value">{(s.success_rate != null ? Math.round(s.success_rate * 100) : 0)}%</div></div>
        <div className="stat-card"><div className="stat-title">Bounces</div><div className="stat-value" style={{ color: '#f97316' }}>{s.total_bounces || 0}</div></div>
        <div className="stat-card"><div className="stat-title">Unsubscribes</div><div className="stat-value" style={{ color: '#f97316' }}>{s.total_unsubscribes || 0}</div></div>
        <div className="stat-card"><div className="stat-title">Spam Reports</div><div className="stat-value" style={{ color: '#ef4444' }}>{s.total_spam || 0}</div></div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 24 }}>
        {/* Volume Over Time */}
        <div className="panel">
          <div className="panel-header"><h3 className="panel-title">Send Volume (Last {days} Days)</h3></div>
          <div className="panel-body" style={{ padding: 0, maxHeight: 320, overflowY: 'auto' }}>
            <table className="excel-table">
              <thead>
                <tr><th>Date</th><th>Sent</th><th>Failed</th><th>Pending</th><th>Rejected</th></tr>
              </thead>
              <tbody>
                {(report?.volume_over_time || []).map((d: any, i: number) => (
                  <tr key={i}>
                    <td style={{ whiteSpace: 'nowrap' }}>{d.date}</td>
                    <td style={{ color: 'var(--green)' }}>{d.sent}</td>
                    <td style={{ color: '#ef4444' }}>{d.failed}</td>
                    <td style={{ color: 'var(--accent)' }}>{d.pending}</td>
                    <td style={{ color: '#6b7280' }}>{d.rejected}</td>
                  </tr>
                ))}
                {(report?.volume_over_time || []).length === 0 && (
                  <tr><td colSpan={5} style={{ textAlign: 'center', color: 'var(--muted-slate)', padding: 24 }}>No data yet</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Domain Analytics */}
        <div className="panel">
          <div className="panel-header"><h3 className="panel-title">Top Domains</h3></div>
          <div className="panel-body" style={{ padding: 0, maxHeight: 320, overflowY: 'auto' }}>
            <table className="excel-table">
              <thead>
                <tr><th>Domain</th><th>Total</th><th>Sent</th><th>Failed</th><th>Bounce Rate</th></tr>
              </thead>
              <tbody>
                {(report?.domain_analytics || []).map((d: any, i: number) => (
                  <tr key={i}>
                    <td>{d.domain}</td>
                    <td>{d.total}</td>
                    <td style={{ color: 'var(--green)' }}>{d.sent}</td>
                    <td style={{ color: '#ef4444' }}>{d.failed}</td>
                    <td style={{ color: (d.bounce_rate || 0) > 0.1 ? '#ef4444' : 'var(--green)' }}>
                      {d.bounce_rate != null ? Math.round(d.bounce_rate * 100) + '%' : '0%'}
                    </td>
                  </tr>
                ))}
                {(report?.domain_analytics || []).length === 0 && (
                  <tr><td colSpan={5} style={{ textAlign: 'center', color: 'var(--muted-slate)', padding: 24 }}>No data yet</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 24 }}>
        {/* Hourly Distribution */}
        <div className="panel">
          <div className="panel-header"><h3 className="panel-title">Hourly Send Distribution (UTC)</h3></div>
          <div className="panel-body" style={{ padding: 0, maxHeight: 320, overflowY: 'auto' }}>
            <table className="excel-table">
              <thead>
                <tr><th>Hour</th><th>Sends</th><th style={{ width: '60%' }}>Distribution</th></tr>
              </thead>
              <tbody>
                {(report?.hourly_distribution || []).map((h: any, i: number) => {
                  const maxCount = Math.max(...(report?.hourly_distribution || []).map((x: any) => x.count), 1);
                  const pct = maxCount > 0 ? (h.count / maxCount) * 100 : 0;
                  return (
                    <tr key={i}>
                      <td>{String(h.hour).padStart(2, '0')}:00</td>
                      <td>{h.count}</td>
                      <td>
                        <div style={{
                          height: 18, backgroundColor: 'var(--accent)', borderRadius: 4,
                          width: `${pct}%`, minWidth: h.count > 0 ? 20 : 0,
                          display: 'flex', alignItems: 'center', paddingLeft: 6,
                          color: '#fff', fontSize: 10, fontWeight: 600,
                        }}>
                          {h.count > 0 ? `${Math.round(pct)}%` : ''}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Follow-up & Schedule Stats */}
        <div>
          {/* Follow-up Performance */}
          <div className="panel" style={{ marginBottom: 16 }}>
            <div className="panel-header"><h3 className="panel-title">Follow-up Performance</h3></div>
            <div className="panel-body">
              {report?.follow_up_performance ? (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
                  <div><div style={{ fontSize: 11, color: 'var(--muted-slate)' }}>Total</div><div style={{ fontSize: 20, fontWeight: 600 }}>{report.follow_up_performance.total || 0}</div></div>
                  <div><div style={{ fontSize: 11, color: 'var(--muted-slate)' }}>Sent</div><div style={{ fontSize: 20, fontWeight: 600, color: 'var(--green)' }}>{report.follow_up_performance.sent || 0}</div></div>
                  <div><div style={{ fontSize: 11, color: 'var(--muted-slate)' }}>Pending</div><div style={{ fontSize: 20, fontWeight: 600, color: 'var(--accent)' }}>{report.follow_up_performance.pending || 0}</div></div>
                  <div><div style={{ fontSize: 11, color: 'var(--muted-slate)' }}>Skipped</div><div style={{ fontSize: 20, fontWeight: 600, color: '#6b7280' }}>{report.follow_up_performance.skipped || 0}</div></div>
                </div>
              ) : <p style={{ color: 'var(--muted-slate)', fontSize: 13 }}>No follow-up data</p>}
            </div>
          </div>

          {/* Schedule Stats */}
          <div className="panel">
            <div className="panel-header"><h3 className="panel-title">Schedule Queue</h3></div>
            <div className="panel-body">
              {report?.schedule_stats ? (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
                  <div><div style={{ fontSize: 11, color: 'var(--muted-slate)' }}>Total</div><div style={{ fontSize: 20, fontWeight: 600 }}>{report.schedule_stats.total || 0}</div></div>
                  <div><div style={{ fontSize: 11, color: 'var(--muted-slate)' }}>Pending</div><div style={{ fontSize: 20, fontWeight: 600, color: 'var(--accent)' }}>{report.schedule_stats.pending || 0}</div></div>
                  <div><div style={{ fontSize: 11, color: 'var(--muted-slate)' }}>Sent</div><div style={{ fontSize: 20, fontWeight: 600, color: 'var(--green)' }}>{report.schedule_stats.sent || 0}</div></div>
                  <div><div style={{ fontSize: 11, color: 'var(--muted-slate)' }}>Cancelled</div><div style={{ fontSize: 20, fontWeight: 600, color: '#6b7280' }}>{report.schedule_stats.cancelled || 0}</div></div>
                </div>
              ) : <p style={{ color: 'var(--muted-slate)', fontSize: 13 }}>No schedule data</p>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
