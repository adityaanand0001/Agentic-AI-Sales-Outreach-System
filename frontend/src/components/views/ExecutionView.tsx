'use client';

interface Props {
  execViz: string; execLeads: any[];
  execEmail: { subject: string; to: string; body: string };
  onClose: () => void; processingExec: boolean;
}

const STEPS = ['Lead Selection', 'AI Generation', 'Compliance Check', 'Ready to Send'];
const STEP_MAP: Record<string, number> = { complete: 3, generating: 1, compliance: 2 };

export default function ExecutionView({ execViz, execLeads, execEmail, onClose, processingExec }: Props) {
  const ai = STEP_MAP[execViz] ?? 0;
  const S = { opacity: 0.8 };

  return (
    <div className="view-content">
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 className="panel-title">Execution Visualizer</h2>
        <button className="btn btn-ghost" onClick={onClose}>Close</button>
      </div>
      <div className="execution-layout">
        <div className="process-stepper">
          <h3 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, color: 'var(--matte-black)' }}>Process Steps</h3>
          {STEPS.map((step, i) => (
            <div key={step} className={`step-item ${ai === i ? 'active' : ''} ${i < ai ? 'completed' : ''}`}>
              <div className="step-icon">{i < ai
                ? <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12"/></svg>
                : i + 1}</div>
              <div>
                <div className="step-name">{step}</div>
                <div className="step-desc">{i === ai ? (processingExec ? 'Processing...' : 'Active') : i < ai ? 'Completed' : 'Pending'}</div>
              </div>
            </div>
          ))}
          {processingExec && <div className="mono-label" style={{ textAlign: 'center', marginTop: 8, color: 'var(--interaction-blue)' }}>Processing...</div>}
        </div>
        <div className="visualizer-canvas">
          {processingExec && execViz === 'generating' ? (
            <div><div className="cohere-pulse" style={{ marginBottom: 16 }} /><p style={S}>Generating email content...</p></div>
          ) : execViz === 'complete' && execEmail.to ? (
            <div id="viz-generate">
              <div className="priority-list" style={{ padding: 24 }}>
                <h3 style={{ fontSize: 14, fontWeight: 500, marginBottom: 12, textAlign: 'center', ...S }}>Generated Email Preview</h3>
                <div className="priority-item" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 8 }}>
                  <div style={{ fontSize: 11, opacity: 0.6 }}>To: {execEmail.to}</div>
                  <div style={{ fontWeight: 500, fontSize: 13 }}>{execEmail.subject}</div>
                  <div style={{ fontSize: 12, opacity: 0.7, lineHeight: 1.5, whiteSpace: 'pre-wrap', maxHeight: 160, overflow: 'auto' }}>{execEmail.body}</div>
                </div>
              </div>
            </div>
          ) : execLeads.length > 0 && execViz === 'selection' ? (
            <div className="priority-list">
              <h3 style={{ fontSize: 14, fontWeight: 500, marginBottom: 8, textAlign: 'center', ...S }}>Selected Leads ({execLeads.length})</h3>
              {execLeads.map((lead, i) => (
                <div key={i} className="priority-item" style={{ animationDelay: `${i * 0.1}s` }}>
                  <div>
                    <div style={{ fontWeight: 500, fontSize: 13 }}>{lead.name || lead.first_name || 'Unknown'}</div>
                    <div style={{ fontSize: 11, opacity: 0.6 }}>{lead.company || lead.email || ''}</div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div>
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ opacity: 0.3, marginBottom: 16 }}>
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" /></svg>
              <p style={{ opacity: 0.5, fontSize: 13 }}>Run the agent to see execution visualization</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
