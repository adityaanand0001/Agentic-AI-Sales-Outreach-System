'use client';

interface Props {
  data: any | null;
}

export default function WarmupView({ data }: Props) {
  const score = data?.warmup_score ?? data?.score ?? 0;
  const sent = data?.emails_sent ?? data?.total_sent ?? 0;
  const replies = data?.replies_received ?? data?.replies ?? 0;
  const bounceRate = data?.bounce_rate ?? 0;
  const reputation = data?.reputation ?? data?.score ?? 0;
  const daily = data?.daily_activity ?? data?.daily ?? [];
  const radius = 85;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - score / 100);

  const repLabel = reputation > 70 ? 'Good' : reputation > 40 ? 'Fair' : 'Poor';
  const repColor = reputation > 70 ? '#166534' : reputation > 40 ? '#854d0e' : '#991b1b';
  const repBg = reputation > 70 ? '#dcfce7' : reputation > 40 ? '#fef9c3' : '#fee2e2';

  return (
    <div className="view-content">
      <h2 className="panel-title" style={{ marginBottom: 24 }}>Warmup Dashboard</h2>
      <div className="warmup-layout">
        <div className="panel">
          <div className="panel-header"><h3 className="panel-title">Warmup Gauge</h3></div>
          <div className="panel-body" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 32 }}>
            <div style={{ position: 'relative', width: 200, height: 200 }}>
              <svg width="200" height="200" viewBox="0 0 200 200">
                <circle cx="100" cy="100" r={radius} fill="none" stroke="#e4e4e7" strokeWidth="16" />
                <circle cx="100" cy="100" r={radius} fill="none" stroke="#2563eb" strokeWidth="16"
                  strokeDasharray={circumference} strokeDashoffset={offset}
                  transform="rotate(-90 100 100)" strokeLinecap="round"
                  style={{ transition: 'stroke-dashoffset 1s ease' }} />
                <text x="100" y="95" textAnchor="middle" fontSize="36" fontWeight="700" fill="#111111">
                  {Math.round(score)}
                </text>
                <text x="100" y="118" textAnchor="middle" fontSize="12" fill="#71717a">/ 100</text>
              </svg>
            </div>
          </div>
        </div>
        <div className="panel">
          <div className="panel-header"><h3 className="panel-title">Status</h3></div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div className="warmup-status-row">
              <div className="warmup-status-item">
                <div className="label">Emails Sent</div>
                <div className="value">{sent}</div>
              </div>
              <div className="warmup-status-item">
                <div className="label">Replies</div>
                <div className="value">{replies}</div>
              </div>
              <div className="warmup-status-item">
                <div className="label">Bounce Rate</div>
                <div className="value">{Math.round(bounceRate * 100)}%</div>
              </div>
            </div>
            <div className="warmup-status-item" style={{ border: 'none', padding: '8px 0', boxShadow: 'none' }}>
              <div className="label">Sender Reputation</div>
              <div className="value" style={{ fontSize: 14 }}>
                <span style={{ padding: '2px 10px', borderRadius: 12, fontWeight: 600, background: repBg, color: repColor }}>
                  {repLabel}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="panel warmup-full">
        <div className="panel-header"><h3 className="panel-title">14-Day Volume</h3></div>
        <div className="panel-body">
          <div className="warmup-chart">
            {daily.length > 0 ? daily.map((d: any, i: number) => (
              <div key={i} className="bar" style={{
                height: Math.max(8, (d.count || d.sent || 0) * 3),
                background: (d.count || d.sent || 0) > 0
                  ? 'linear-gradient(180deg, #2563eb, #7c3aed)' : '#e4e4e7',
              }} />
            )) : (
              <div style={{ width: '100%', textAlign: 'center', color: 'var(--muted-slate)', padding: 40 }}>
                No daily activity data available yet.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
