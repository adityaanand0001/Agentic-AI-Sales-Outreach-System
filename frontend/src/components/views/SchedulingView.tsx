'use client';

import { useState, useEffect, useCallback } from 'react';
import * as api from '@/lib/api';

interface Props {
  toast: (msg: string) => void;
}

export default function SchedulingView({ toast }: Props) {
  const [items, setItems] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [filter, setFilter] = useState<string>('');
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [pendingTrackers, setPendingTrackers] = useState<any[]>([]);
  const [selectedTrackerId, setSelectedTrackerId] = useState('');
  const [scheduleDate, setScheduleDate] = useState('');
  const [scheduleTime, setScheduleTime] = useState('');

  const load = useCallback(() => {
    api.scheduling.list(filter || undefined).then(setItems).catch(() => {});
    api.scheduling.summary().then(setSummary).catch(() => {});
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const openScheduleModal = async () => {
    try {
      const trackers = await api.tracker.list('PENDING');
      setPendingTrackers(trackers);
      if (trackers.length > 0) {
        setSelectedTrackerId(trackers[0].id);
      }
      // Default to 1 hour from now
      const d = new Date(Date.now() + 3600000);
      setScheduleDate(d.toISOString().slice(0, 10));
      setScheduleTime(d.toISOString().slice(11, 16));
      setShowScheduleModal(true);
    } catch { toast('Failed to load pending emails'); }
  };

  const handleSchedule = async () => {
    if (!selectedTrackerId || !scheduleDate || !scheduleTime) {
      toast('Please fill in all fields');
      return;
    }
    try {
      const scheduledAt = new Date(`${scheduleDate}T${scheduleTime}`).toISOString();
      await api.scheduling.schedule(selectedTrackerId, scheduledAt);
      toast('Email scheduled for delivery');
      setShowScheduleModal(false);
      load();
      // Refresh the queue badge too
    } catch (e: any) {
      toast(e.message);
    }
  };

  const handleCancel = async (id: string) => {
    if (!confirm('Cancel this scheduled send?')) return;
    try {
      await api.scheduling.cancel(id);
      toast('Scheduled send cancelled');
      load();
    } catch (e: any) {
      toast(e.message);
    }
  };

  const handleProcessDue = async () => {
    try {
      const r = await api.scheduling.processDue();
      toast(`Processed ${r.processed} due sends`);
      load();
    } catch (e: any) {
      toast(e.message);
    }
  };

  // Format datetime for display
  const fmt = (iso: string) => {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  };

  const isOverdue = (iso: string, status: string) => {
    if (status !== 'PENDING') return false;
    return new Date(iso).getTime() < Date.now();
  };

  return (
    <div className="view-content">
      {/* Header */}
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 className="panel-title">Smart Send Scheduling</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-solid" onClick={openScheduleModal}>+ Schedule Send</button>
          <button className="btn btn-ghost" onClick={handleProcessDue}>Process Due</button>
          <button className="btn btn-ghost" onClick={load}>Refresh</button>
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(5, 1fr)', marginBottom: 24 }}>
          <div className="stat-card">
            <div className="stat-title">Total</div>
            <div className="stat-value">{summary.total || 0}</div>
          </div>
          <div className="stat-card" style={{ borderLeft: '3px solid var(--blue)' }}>
            <div className="stat-title">Pending</div>
            <div className="stat-value">{summary.pending || 0}</div>
          </div>
          <div className="stat-card" style={{ borderLeft: '3px solid var(--green)' }}>
            <div className="stat-title">Sent</div>
            <div className="stat-value">{summary.sent || 0}</div>
          </div>
          <div className="stat-card" style={{ borderLeft: '3px solid var(--muted-slate)' }}>
            <div className="stat-title">Cancelled</div>
            <div className="stat-value">{summary.cancelled || 0}</div>
          </div>
          <div className="stat-card" style={{ borderLeft: '3px solid #ef4444' }}>
            <div className="stat-title">Failed</div>
            <div className="stat-value">{summary.failed || 0}</div>
          </div>
        </div>
      )}

      {/* Filter tabs */}
      <div className="filter-row" style={{ marginBottom: 16 }}>
        {['', 'PENDING', 'SENT', 'CANCELLED', 'FAILED'].map(s => (
          <button
            key={s}
            className={`btn ${filter === s ? 'btn-solid' : 'btn-ghost'}`}
            onClick={() => setFilter(s)}
            style={{ fontSize: 12, padding: '4px 12px' }}
          >
            {s || 'All'}
          </button>
        ))}
      </div>

      {/* Schedule list */}
      <div className="panel">
        <div className="panel-body" style={{ padding: 0 }}>
          {items.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--muted-slate)' }}>
              No scheduled sends yet. Approve an email and schedule it for later delivery.
            </div>
          ) : (
            <table className="excel-table">
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Email</th>
                  <th>Subject</th>
                  <th>Scheduled</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map(item => (
                  <tr key={item.id} className={isOverdue(item.scheduled_at, item.status) ? 'overdue-row' : ''}>
                    <td style={{ fontWeight: 500 }}>{item.company_name || '-'}</td>
                    <td style={{ color: 'var(--muted-slate)', fontSize: 12 }}>{item.email || '-'}</td>
                    <td style={{ maxWidth: 250, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {item.email_subject || '-'}
                    </td>
                    <td>
                      <span className={`mono-label ${isOverdue(item.scheduled_at, item.status) ? 'overdue' : ''}`}>
                        {fmt(item.scheduled_at)}
                        {isOverdue(item.scheduled_at, item.status) && ' ⚠️ OVERDUE'}
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${item.status === 'PENDING' ? 'badge-warning' : item.status === 'SENT' ? 'badge-success' : item.status === 'CANCELLED' ? '' : 'badge-error'}`}>
                        {item.status}
                      </span>
                    </td>
                    <td>
                      {item.status === 'PENDING' && (
                        <button className="btn btn-ghost" style={{ color: '#ef4444', fontSize: 11, padding: '3px 10px' }} onClick={() => handleCancel(item.id)}>
                          Cancel
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Schedule Modal */}
      {showScheduleModal && (
        <div className="modal-overlay" onClick={() => setShowScheduleModal(false)}>
          <div className="modal-card" onClick={e => e.stopPropagation()} style={{ maxWidth: 480 }}>
            <div className="modal-header">
              <h3 className="panel-title">Schedule Email Send</h3>
              <button className="btn btn-ghost" onClick={() => setShowScheduleModal(false)}>✕</button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label className="form-label">Select Pending Email</label>
                <select
                  className="form-input"
                  value={selectedTrackerId}
                  onChange={e => setSelectedTrackerId(e.target.value)}
                >
                  {pendingTrackers.map((t: any) => (
                    <option key={t.id} value={t.id}>
                      {t.company_name || t.email} — {(t.email_subject || '').slice(0, 50)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-row" style={{ display: 'flex', gap: 12 }}>
                <div className="form-group" style={{ flex: 1 }}>
                  <label className="form-label">Date</label>
                  <input
                    type="date"
                    className="form-input"
                    value={scheduleDate}
                    onChange={e => setScheduleDate(e.target.value)}
                    min={new Date().toISOString().slice(0, 10)}
                  />
                </div>
                <div className="form-group" style={{ flex: 1 }}>
                  <label className="form-label">Time</label>
                  <input
                    type="time"
                    className="form-input"
                    value={scheduleTime}
                    onChange={e => setScheduleTime(e.target.value)}
                  />
                </div>
              </div>
            </div>
            <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, padding: '12px 20px', borderTop: '1px solid var(--border)' }}>
              <button className="btn btn-ghost" onClick={() => setShowScheduleModal(false)}>Cancel</button>
              <button className="btn btn-solid" onClick={handleSchedule}>Schedule Send</button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        .overdue-row { background: rgba(239, 68, 68, 0.04); }
        .overdue { color: #ef4444; font-weight: 600; }
        .badge-warning { background: #fef3c7; color: #92400e; border-radius: 4px; padding: 2px 8px; font-size: 11px; }
        .badge-success { background: #d1fae5; color: #065f46; border-radius: 4px; padding: 2px 8px; font-size: 11px; }
        .badge-error { background: #fef2f2; color: #991b1b; border-radius: 4px; padding: 2px 8px; font-size: 11px; }
        .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
        .modal-card { background: white; border-radius: 12px; box-shadow: 0 20px 60px rgba(0,0,0,0.15); width: 100%; }
        .modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border); }
        .modal-body { padding: 20px; }
        .form-group { margin-bottom: 16px; }
        .form-label { display: block; font-size: 12px; font-weight: 600; color: var(--muted-slate); margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
        .form-input { width: 100%; padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px; font-size: 14px; background: white; }
        .form-input:focus { outline: none; border-color: var(--blue); }
        select.form-input { appearance: auto; }
      `}</style>
    </div>
  );
}
