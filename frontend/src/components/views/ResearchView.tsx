'use client';

import { useState, useEffect, useRef, useCallback } from 'react';

interface Props {
  toast: (s: string) => void;
}

export default function ResearchView({ toast }: Props) {
  const [activeSection, setActiveSection] = useState<'upload' | 'single' | 'briefs'>('upload');
  const [uploading, setUploading] = useState(false);
  const [batchId, setBatchId] = useState<string | null>(null);
  const [progress, setProgress] = useState<any>(null);
  const [briefs, setBriefs] = useState<any[]>([]);
  const [selectedBrief, setSelectedBrief] = useState<any | null>(null);
  const [singleForm, setSingleForm] = useState({ name: '', sector: '', size: '' });
  const [researching, setResearching] = useState(false);
  const [singleResult, setSingleResult] = useState<any | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Load recent briefs on mount
  useEffect(() => {
    const { research } = await_import();
    research.briefs(0, 20).then(setBriefs).catch(() => {});
  }, []);

  const await_import = () => import('@/lib/api').then(m => m.research);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.endsWith('.csv')) { toast('Only CSV files accepted'); return; }
    setUploading(true);
    try {
      const api = await await_import();
      const res = await api.uploadCsv(file);
      setBatchId(res.batch_id);
      toast(`Research started for ${res.total_leads} leads`);
      pollRef.current = setInterval(async () => {
        try {
          const p = await api.batchProgress(res.batch_id);
          setProgress(p);
          if (p.status === 'COMPLETED' || p.status === 'FAILED') {
            if (pollRef.current) clearInterval(pollRef.current);
            toast(`Batch ${p.status}: ${p.processed}/${p.total_leads} processed`);
          }
        } catch {}
      }, 2000);
    } catch (e: any) { toast(e.message); }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = ''; }
  };

  const handleSingleResearch = async () => {
    if (!singleForm.name.trim()) { toast('Company name is required'); return; }
    setResearching(true);
    setSingleResult(null);
    try {
      const api = await await_import();
      const result = await api.single(singleForm.name, singleForm.sector, singleForm.size);
      setSingleResult(result);
      toast('Research complete');
    } catch (e: any) { toast(e.message); }
    finally { setResearching(false); }
  };

  const loadBriefs = useCallback(async () => {
    try {
      const api = await await_import();
      const data = await api.briefs(0, 20);
      setBriefs(data);
    } catch {}
  }, []);

  const selectBrief = async (id: string) => {
    try {
      const api = await await_import();
      const data = await api.brief(id);
      setSelectedBrief(data);
    } catch (e: any) { toast('Failed to load brief'); }
  };

  const confidenceColor = (c: number) =>
    c >= 0.7 ? '#059669' : c >= 0.4 ? '#d97706' : '#dc2626';

  return (
    <div className="view-content" style={{ padding: 0, height: 'calc(100vh - 64px)', display: 'flex', flexDirection: 'column' }}>
      {/* Toolbar */}
      <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--border-light)', background: 'white', display: 'flex', gap: 8, alignItems: 'center' }}>
        <h2 className="panel-title">Deep Research</h2>
        <div style={{ flex: 1 }} />
        {[
          { id: 'upload', label: 'CSV Upload' },
          { id: 'single', label: 'Single Lead' },
          { id: 'briefs', label: 'Research Briefs' },
        ].map(t => (
          <button key={t.id}
            className={`btn ${activeSection === t.id ? 'btn-solid' : 'btn-ghost'}`}
            onClick={() => setActiveSection(t.id as any)}
            style={{ fontSize: 11 }}>
            {t.label}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: 24 }}>
        {/* ── CSV Upload Section ── */}
        {activeSection === 'upload' && (
          <div>
            <div className="card" style={{ maxWidth: 600, marginBottom: 24 }}>
              <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>Upload CSV for Batch Research</h3>
              <p style={{ fontSize: 12, color: 'var(--muted-slate)', marginBottom: 16 }}>
                CSV columns: <code>name</code>, <code>sector</code>, <code>size</code> (or <code>Name</code>, <code>Company</code>, <code>Industry</code>)
              </p>
              <input ref={fileRef} type="file" accept=".csv" onChange={handleUpload}
                style={{ marginBottom: 12 }} disabled={uploading} />
              {uploading && <div className="mono-label" style={{ color: 'var(--interaction-blue)' }}>Uploading & starting pipeline...</div>}
            </div>

            {batchId && progress && (
              <div className="card" style={{ maxWidth: 600 }}>
                <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>
                  Batch Progress
                  <span className="mono-label" style={{ marginLeft: 8, fontSize: 10, color: 'var(--muted-slate)' }}>{batchId}</span>
                </h3>
                <div style={{ marginBottom: 8, height: 6, background: '#e5e7eb', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{
                    height: '100%', borderRadius: 3,
                    width: `${progress.total_leads > 0 ? (progress.processed / progress.total_leads) * 100 : 0}%`,
                    background: progress.status === 'FAILED' ? '#ef4444' : '#059669',
                    transition: 'width 0.5s ease',
                  }} />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, fontSize: 12 }}>
                  <div><span style={{ color: 'var(--muted-slate)' }}>Status</span><br /><strong>{progress.status}</strong></div>
                  <div><span style={{ color: 'var(--muted-slate)' }}>Processed</span><br /><strong>{progress.processed}/{progress.total_leads}</strong></div>
                  <div><span style={{ color: 'var(--muted-slate)' }}>Contacts</span><br /><strong>{progress.contacts_found}</strong></div>
                  <div><span style={{ color: 'var(--muted-slate)' }}>Errors</span><br /><strong style={{ color: progress.errors > 0 ? '#ef4444' : 'inherit' }}>{progress.errors}</strong></div>
                </div>
                {progress.lead_results?.length > 0 && (
                  <div style={{ marginTop: 16 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 8, color: 'var(--muted-slate)' }}>Latest Results</div>
                    {progress.lead_results.slice(0, 10).map((r: any, i: number) => (
                      <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border-light)', fontSize: 12 }}>
                        <span>{r.name || '-'}</span>
                        <span style={{ color: r.status === 'completed' ? '#059669' : '#ef4444' }}>
                          {r.email || r.status || r.error || '-'}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── Single Lead Section ── */}
        {activeSection === 'single' && (
          <div style={{ maxWidth: 500 }}>
            <div className="card" style={{ marginBottom: 24 }}>
              <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>Single Lead Research</h3>
              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 11, fontWeight: 600, display: 'block', marginBottom: 4 }}>Company Name *</label>
                <input className="form-input" value={singleForm.name}
                  onChange={e => setSingleForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="e.g. Acme Corp" style={{ width: '100%' }} />
              </div>
              <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 11, fontWeight: 600, display: 'block', marginBottom: 4 }}>Sector</label>
                <input className="form-input" value={singleForm.sector}
                  onChange={e => setSingleForm(f => ({ ...f, sector: e.target.value }))}
                  placeholder="e.g. SaaS, Fintech" style={{ width: '100%' }} />
              </div>
              <div style={{ marginBottom: 16 }}>
                <label style={{ fontSize: 11, fontWeight: 600, display: 'block', marginBottom: 4 }}>Size</label>
                <input className="form-input" value={singleForm.size}
                  onChange={e => setSingleForm(f => ({ ...f, size: e.target.value }))}
                  placeholder="e.g. 50-200 employees" style={{ width: '100%' }} />
              </div>
              <button className="btn btn-solid" onClick={handleSingleResearch}
                disabled={researching || !singleForm.name.trim()} style={{ fontSize: 12 }}>
                {researching ? 'Researching...' : 'Run Research'}
              </button>
            </div>

            {researching && (
              <div className="card" style={{ textAlign: 'center', padding: 32 }}>
                <div className="cohere-pulse" style={{ margin: '0 auto 12px' }} />
                <div className="mono-label" style={{ color: 'var(--interaction-blue)' }}>Researching {singleForm.name}...</div>
              </div>
            )}

            {singleResult && !researching && (
              <div className="card">
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                  <h3 style={{ fontSize: 16, fontWeight: 600 }}>{singleResult.lead_name}</h3>
                  <span style={{
                    fontSize: 11, padding: '3px 10px', borderRadius: 10,
                    background: confidenceColor(singleResult.confidence ?? 0) + '18',
                    color: confidenceColor(singleResult.confidence ?? 0),
                    fontWeight: 600,
                  }}>
                    {(singleResult.confidence * 100).toFixed(0)}% confidence
                  </span>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20, fontSize: 13 }}>
                  {singleResult.lead_email && (
                    <div><span style={{ color: 'var(--muted-slate)', fontSize: 11 }}>Email</span><br />{singleResult.lead_email}</div>
                  )}
                  {singleResult.person?.person_name && (
                    <div><span style={{ color: 'var(--muted-slate)', fontSize: 11 }}>Contact</span><br />{singleResult.person.person_name} {singleResult.person.role ? `- ${singleResult.person.role}` : ''}</div>
                  )}
                  {singleResult.identity?.domain && (
                    <div><span style={{ color: 'var(--muted-slate)', fontSize: 11 }}>Domain</span><br />{singleResult.identity.domain}</div>
                  )}
                  {singleResult.identity?.location && (
                    <div><span style={{ color: 'var(--muted-slate)', fontSize: 11 }}>Location</span><br />{singleResult.identity.location}</div>
                  )}
                </div>

                {singleResult.profile && (
                  <div style={{ marginBottom: 16 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted-slate)', marginBottom: 4 }}>Profile</div>
                    <p style={{ fontSize: 13, lineHeight: 1.5 }}>{singleResult.profile}</p>
                  </div>
                )}

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
                  {singleResult.why_now?.length > 0 && (
                    <div>
                      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted-slate)', marginBottom: 4 }}>Why Now</div>
                      <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
                        {singleResult.why_now.map((w: string, i: number) => <li key={i}>{w}</li>)}
                      </ul>
                    </div>
                  )}
                  {singleResult.pain_points?.length > 0 && (
                    <div>
                      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted-slate)', marginBottom: 4 }}>Pain Points</div>
                      <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
                        {singleResult.pain_points.map((p: string, i: number) => <li key={i}>{p}</li>)}
                      </ul>
                    </div>
                  )}
                </div>

                {singleResult.hooks?.length > 0 && (
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted-slate)', marginBottom: 4 }}>Personalized Hooks</div>
                    {singleResult.hooks.map((h: any, i: number) => (
                      <div key={i} style={{
                        padding: '8px 12px', marginBottom: 6, borderRadius: 6,
                        background: '#f0fdf4', border: '1px solid #bbf7d0',
                        fontSize: 13, lineHeight: 1.4,
                      }}>
                        {typeof h === 'string' ? h : h.hook}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── Research Briefs Section ── */}
        {activeSection === 'briefs' && (
          <div style={{ display: 'flex', height: '100%', gap: 0 }}>
            <div style={{ flex: selectedBrief ? '0 0 35%' : 1, overflow: 'auto', borderRight: selectedBrief ? '1px solid var(--border-light)' : 'none' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <h3 style={{ fontSize: 14, fontWeight: 600 }}>Recent Research Briefs</h3>
                <button className="btn btn-ghost" onClick={loadBriefs} style={{ fontSize: 10 }}>Refresh</button>
              </div>
              {briefs.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-title">No research briefs yet</div>
                  <div className="empty-description">Upload a CSV or research a single lead to generate briefs.</div>
                </div>
              ) : (
                briefs.map(b => (
                  <div key={b.id}
                    onClick={() => selectBrief(b.id)}
                    style={{
                      padding: '12px 16px', cursor: 'pointer', borderBottom: '1px solid var(--border-light)',
                      background: selectedBrief?.id === b.id ? '#f0f9ff' : 'white',
                      borderLeft: selectedBrief?.id === b.id ? '3px solid #2563eb' : '3px solid transparent',
                    }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <span style={{ fontWeight: 600, fontSize: 13 }}>{b.lead_name}</span>
                      <span style={{
                        fontSize: 10, padding: '2px 8px', borderRadius: 8,
                        background: confidenceColor(b.confidence ?? 0) + '18',
                        color: confidenceColor(b.confidence ?? 0),
                        fontWeight: 600,
                      }}>
                        {(b.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--muted-slate)', display: 'flex', gap: 12 }}>
                      {b.person_name && <span>{b.person_name}</span>}
                      {b.company_domain && <span>{b.company_domain}</span>}
                    </div>
                  </div>
                ))
              )}
            </div>

            {selectedBrief && (
              <div style={{ flex: 1, overflow: 'auto', padding: '0 24px' }}>
                <div className="detail-toolbar" style={{ justifyContent: 'space-between' }}>
                  <span className="mono-label">Research Brief Detail</span>
                  <button className="toolbar-btn" onClick={() => setSelectedBrief(null)} style={{ fontSize: 10 }}>Close</button>
                </div>
                <div style={{ padding: '16px 0' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                    <h3 style={{ fontSize: 18, fontWeight: 600 }}>{selectedBrief.lead_name}</h3>
                    <span style={{
                      fontSize: 11, padding: '3px 10px', borderRadius: 10,
                      background: confidenceColor(selectedBrief.confidence ?? 0) + '18',
                      color: confidenceColor(selectedBrief.confidence ?? 0),
                      fontWeight: 600,
                    }}>
                      {(selectedBrief.confidence * 100).toFixed(0)}% confidence
                    </span>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24, fontSize: 13 }}>
                    {selectedBrief.lead_email && (
                      <div><span style={{ fontSize: 10, color: 'var(--muted-slate)' }}>EMAIL</span><br />{selectedBrief.lead_email}</div>
                    )}
                    {selectedBrief.person_name && (
                      <div><span style={{ fontSize: 10, color: 'var(--muted-slate)' }}>CONTACT</span><br />{selectedBrief.person_name} {selectedBrief.person_role ? `(${selectedBrief.person_role})` : ''}</div>
                    )}
                    {selectedBrief.company_domain && (
                      <div><span style={{ fontSize: 10, color: 'var(--muted-slate)' }}>DOMAIN</span><br />{selectedBrief.company_domain}</div>
                    )}
                    {selectedBrief.company_location && (
                      <div><span style={{ fontSize: 10, color: 'var(--muted-slate)' }}>LOCATION</span><br />{selectedBrief.company_location}</div>
                    )}
                    {selectedBrief.company_tech_stack && (
                      <div style={{ gridColumn: '1 / -1' }}>
                        <span style={{ fontSize: 10, color: 'var(--muted-slate)' }}>TECH STACK</span><br />
                        <span style={{ fontSize: 12 }}>
                          {Array.isArray(selectedBrief.company_tech_stack)
                            ? selectedBrief.company_tech_stack.join(', ')
                            : selectedBrief.company_tech_stack || '-'}
                        </span>
                      </div>
                    )}
                  </div>

                  {selectedBrief.profile && (
                    <div style={{ marginBottom: 20 }}>
                      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted-slate)', marginBottom: 4 }}>Profile</div>
                      <p style={{ fontSize: 13, lineHeight: 1.5 }}>{selectedBrief.profile}</p>
                    </div>
                  )}

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
                    {selectedBrief.why_now?.length > 0 && (
                      <div>
                        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted-slate)', marginBottom: 4 }}>Why Now</div>
                        <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
                          {selectedBrief.why_now.map((w: string, i: number) => <li key={i}>{w}</li>)}
                        </ul>
                      </div>
                    )}
                    {selectedBrief.pain_points?.length > 0 && (
                      <div>
                        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted-slate)', marginBottom: 4 }}>Pain Points</div>
                        <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
                          {selectedBrief.pain_points.map((p: string, i: number) => <li key={i}>{p}</li>)}
                        </ul>
                      </div>
                    )}
                  </div>

                  {selectedBrief.hooks?.length > 0 && (
                    <div style={{ marginBottom: 20 }}>
                      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted-slate)', marginBottom: 4 }}>Hooks</div>
                      {selectedBrief.hooks.map((h: any, i: number) => (
                        <div key={i} style={{
                          padding: '8px 12px', marginBottom: 6, borderRadius: 6,
                          background: '#f0fdf4', border: '1px solid #bbf7d0',
                          fontSize: 13, lineHeight: 1.4,
                        }}>
                          {typeof h === 'string' ? h : h.hook || h}
                        </div>
                      ))}
                    </div>
                  )}

                  {selectedBrief.company_description && (
                    <div style={{ marginBottom: 20 }}>
                      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted-slate)', marginBottom: 4 }}>Company Description</div>
                      <p style={{ fontSize: 13, lineHeight: 1.5 }}>{selectedBrief.company_description}</p>
                    </div>
                  )}

                  <div style={{ fontSize: 11, color: 'var(--muted-slate)', marginTop: 16 }}>
                    Total sources: {selectedBrief.total_sources ?? 0} | Sources: {selectedBrief.person_sources?.join(', ') || '-'}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
