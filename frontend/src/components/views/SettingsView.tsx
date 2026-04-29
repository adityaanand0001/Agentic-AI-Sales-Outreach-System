'use client';

interface Props {
  schedulerRunning: boolean;
  schedulerLastRun: string | null;
  onToggleScheduler: () => void;
  onRunNow: () => void;
  threshold: number;
  onThresholdChange: (v: number) => void;
  batchSize: number;
  onBatchSizeChange: (v: number) => void;
  onSave: () => void;
}

export default function SettingsView({
  schedulerRunning, schedulerLastRun, onToggleScheduler, onRunNow,
  threshold, onThresholdChange, batchSize, onBatchSizeChange, onSave,
}: Props) {
  return (
    <div className="view-content">
      <h2 className="panel-title" style={{ marginBottom: 24 }}>Settings</h2>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        <div className="panel">
          <div className="panel-header"><h3 className="panel-title">Scheduler</h3></div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: schedulerRunning ? '#22c55e' : '#ef4444' }} />
              <span>{schedulerRunning ? 'Running' : 'Stopped'}</span>
            </div>
            {schedulerLastRun && (
              <div className="mono-label" style={{ fontSize: 10, color: 'var(--muted-slate)' }}>
                Last run: {new Date(schedulerLastRun).toLocaleString()}
              </div>
            )}
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-solid" onClick={onToggleScheduler}>
                {schedulerRunning ? 'Stop Scheduler' : 'Start Scheduler'}
              </button>
              <button className="btn btn-ghost" onClick={onRunNow}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                Run Now
              </button>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header"><h3 className="panel-title">Agent Parameters</h3></div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div className="form-group">
              <label className="form-label">Auto-Send Confidence Threshold</label>
              <input className="form-input" type="number" min="0" max="1" step="0.05"
                value={threshold} onChange={e => onThresholdChange(parseFloat(e.target.value) || 0.8)} />
            </div>
            <div className="form-group">
              <label className="form-label">Batch Size</label>
              <input className="form-input" type="number" min="1" max="100"
                value={batchSize} onChange={e => onBatchSizeChange(parseInt(e.target.value) || 10)} />
            </div>
            <button className="btn btn-solid" onClick={onSave}>Save Config</button>
          </div>
        </div>
      </div>
    </div>
  );
}
