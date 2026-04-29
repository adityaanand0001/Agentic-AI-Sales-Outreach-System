'use client';

interface Props {
  templates: any[];
  search: string;
  onSearchChange: (v: string) => void;
  selectedTemplate: any | null;
  onSelect: (t: any) => void;
  onNew: () => void;
  form: { name: string; subject: string; body: string };
  onFormChange: (field: string, v: string) => void;
  onSave: () => void;
  onDelete: () => void;
}

const VARIABLES = ['{{first_name}}', '{{last_name}}', '{{company}}', '{{role}}', '{{email}}'];

export default function TemplatesView({
  templates, search, onSearchChange, selectedTemplate, onSelect, onNew,
  form, onFormChange, onSave, onDelete,
}: Props) {
  return (
    <div className="view-content">
      <h2 className="panel-title" style={{ marginBottom: 16 }}>Email Templates</h2>
      <div className="templates-layout">
        <div className="panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="panel-header" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input className="form-input" placeholder="Search templates..." value={search}
              onChange={e => onSearchChange(e.target.value)} style={{ flex: 1 }} />
            <button className="btn btn-solid" onClick={onNew}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              New
            </button>
          </div>
          <div className="template-list-scroll">
            {templates.length === 0 ? (
              <div className="empty-state" style={{ height: 200 }}>
                <div className="empty-title">No templates</div>
                <div className="empty-description">Create your first email template.</div>
              </div>
            ) : templates.map(t => (
              <div key={t.id}
                style={{
                  padding: '12px 16px', borderBottom: '1px solid var(--border-light)', cursor: 'pointer',
                  background: selectedTemplate?.id === t.id ? '#eff6ff' : 'transparent',
                }}
                onClick={() => onSelect(t)}>
                <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 2 }}>{t.name}</div>
                <div style={{ fontSize: 11, color: 'var(--muted-slate)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {t.subject}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="panel" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="panel-header">
            <h3 className="panel-title">{selectedTemplate ? 'Edit Template' : 'New Template'}</h3>
          </div>
          <div className="panel-body" style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div className="form-group">
              <label className="form-label">Name</label>
              <input className="form-input" value={form.name}
                onChange={e => onFormChange('name', e.target.value)} />
            </div>
            <div className="form-group">
              <label className="form-label">Subject</label>
              <input className="form-input" value={form.subject}
                onChange={e => onFormChange('subject', e.target.value)} />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label className="form-label">Body</label>
              <div style={{ marginBottom: 8, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                {VARIABLES.map(v => (
                  <span key={v} className="var-chip" onClick={() => onFormChange('body', form.body + v)}>{v}</span>
                ))}
              </div>
              <textarea className="form-input form-textarea" value={form.body}
                onChange={e => onFormChange('body', e.target.value)} style={{ minHeight: 200 }} />
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-solid" onClick={onSave}>Save</button>
              {selectedTemplate && (
                <button className="btn btn-ghost" style={{ color: '#ef4444' }} onClick={onDelete}>Delete</button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
