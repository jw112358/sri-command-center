import { useEffect, useState } from 'react';
import type { MarketingDashboard } from '../types';
import { getMarketingDashboard, onOperatorSessionChanged, scheduleMarketingApproval, setMarketingApproval, verifyMarketingRoute } from '../api/client';

export function MarketingOS() {
  const [data, setData] = useState<MarketingDashboard | null>(null);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState('');

  const refresh = () => getMarketingDashboard().then(value => {
    setData(value);
    setError('');
  }).catch(() => setError('Sign in to load the private Marketing OS launch console.'));

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 30000);
    const unsubscribe = onOperatorSessionChanged(refresh);
    return () => { window.clearInterval(timer); unsubscribe(); };
  }, []);

  const approve = (id: string, approved: boolean) => {
    setSaving(id);
    setMarketingApproval(id, approved).then(value => {
      setData(value);
      setError('');
    }).catch(() => setError('The approval could not be saved.')).finally(() => setSaving(''));
  };

  const verifyRoute = (platform: string) => {
    const key = `route:${platform}`;
    setSaving(key);
    verifyMarketingRoute(platform).then(refresh).catch(() => {
      setError(`The ${platform.toUpperCase()} publishing route could not be verified.`);
    }).finally(() => setSaving(''));
  };

  const queueAsset = (id: string) => {
    setSaving(id);
    scheduleMarketingApproval(id).then(refresh).catch(() => {
      setError('The approved asset could not be queued. Verify its exact account route first.');
    }).finally(() => setSaving(''));
  };

  if (!data) return <section className="marketing-os"><div className="panel marketing-empty">{error || 'LOADING MARKETING OS…'}</div></section>;
  const approved = data.approvals.filter(item => item.status === 'approved').length;

  return (
    <section className="marketing-os" aria-label="Marketing OS launch console">
      <div className="marketing-summary panel brackets">
        <div className="panel-h"><span className="blip"></span><span className="t">MARKETING OS · GTD-v2 LAUNCH</span><span className="corner">{data.launchStage.toUpperCase()}</span></div>
        <div className="marketing-summary-body">
          <div><span className="marketing-label">PRODUCTION READINESS</span><strong>{data.productionReadiness}%</strong></div>
          <div><span className="marketing-label">OPERATIONAL CAPABILITY</span><strong>{data.minimumOperationalCapability}%</strong></div>
          <div><span className="marketing-label">ASSET APPROVALS</span><strong>{approved}/{data.approvals.length}</strong></div>
          <a className="btn solid" href={data.destination} target="_blank" rel="noreferrer">OPEN GTD LAUNCH DESTINATION ↗</a>
        </div>
        <p className="marketing-objective">{data.objective}</p>
        <p className="marketing-gate"><b>CURRENT GATE:</b> {data.currentGate}</p>
      </div>

      <div className="marketing-grid">
        <div className="panel">
          <div className="panel-h"><span className="t">LAUNCH ASSETS</span><span className="corner">PACKET {data.packetId}</span></div>
          <div className="marketing-assets">
            {data.approvals.map(item => (
              <article className="marketing-asset" key={item.id}>
                <div className="marketing-asset-head"><b>{item.platform.toUpperCase()}</b><span className={'badge ' + (item.status === 'approved' ? 'ACTIVE' : 'IDLE')}>{item.status.replace('-', ' ').toUpperCase()}</span></div>
                <span className="marketing-format">{item.format}</span>
                <p>{item.content}</p>
                <a href={item.destination} target="_blank" rel="noreferrer">PUBLISH DESTINATION ↗</a>
                <small>{item.mediaUrls.length ? `${item.mediaUrls.length} approved media item${item.mediaUrls.length === 1 ? '' : 's'}` : 'Text-only asset'}</small>
                <div className="marketing-actions">
                  {item.status === 'approved' && !data.publications.some(publication => publication.approvalId === item.id && !['failed', 'cancelled'].includes(publication.status)) && (
                    <button className="btn solid sm" disabled={saving === item.id} onClick={() => queueAsset(item.id)}>
                      {saving === item.id ? 'QUEUEING…' : 'QUEUE NEXT VERIFIED SLOT'}
                    </button>
                  )}
                  <button className={item.status === 'approved' ? 'btn sm' : 'btn solid sm'} disabled={saving === item.id} onClick={() => approve(item.id, item.status !== 'approved')}>
                    {saving === item.id ? 'SAVING…' : item.status === 'approved' ? 'REVOKE APPROVAL' : 'APPROVE FOR CONTROLLED LAUNCH'}
                  </button>
                </div>
              </article>
            ))}
          </div>
        </div>
        <div className="panel">
          <div className="panel-h"><span className="t">CONNECTORS &amp; MEASUREMENT</span></div>
          <div className="marketing-connectors">
            {data.connectors.map(connector => (
              <div className="marketing-connector" key={connector.name}>
                <div><b>{connector.name}</b><span className={'badge ' + (connector.status === 'READY' ? 'ACTIVE' : connector.status === 'BLOCKED' ? 'BLOCKED' : 'IDLE')}>{connector.status}</span></div>
                <p>{connector.detail}</p>
              </div>
            ))}
            {data.routes.map(route => (
              <div className="marketing-connector" key={`route:${route.platform}`}>
                <div><b>{route.platform.toUpperCase()} ACCOUNT ROUTE</b><span className={'badge ' + (route.verified ? 'ACTIVE' : route.configured ? 'IDLE' : 'BLOCKED')}>{route.verified ? 'VERIFIED' : route.configured ? 'VERIFY' : 'NOT CONFIGURED'}</span></div>
                <p>{route.detail}</p>
                {route.configured && !route.verified && <button className="btn sm" disabled={saving === `route:${route.platform}`} onClick={() => verifyRoute(route.platform)}>{saving === `route:${route.platform}` ? 'VERIFYING…' : 'VERIFY EXACT ROUTE'}</button>}
              </div>
            ))}
            <div className="marketing-measure"><span className="marketing-label">MEASUREMENT SOURCE</span><p>{data.measurementSource}</p></div>
            {error && <p className="marketing-error">{error}</p>}
          </div>
        </div>
      </div>

      <div className="marketing-operations panel">
        <div className="panel-h"><span className="t">AGENT OPERATIONS</span><span className="corner">PUBLISH → EVIDENCE → LEARN</span></div>
        <div className="marketing-operations-grid">
          <div>
            <span className="marketing-label">PUBLISHING AGENT</span>
            {data.publications.length === 0 ? <p className="marketing-empty">No asset has entered the publishing queue.</p> : data.publications.map(item => (
              <article className="marketing-operation" key={item.id}>
                <div><b>{item.platform.toUpperCase()}</b><span className={`badge ${item.status === 'published' ? 'ACTIVE' : item.status === 'failed' ? 'BLOCKED' : 'IDLE'}`}>{item.status.toUpperCase()}</span></div>
                <small>{item.scheduledTime ? `Scheduled ${new Date(item.scheduledTime).toLocaleString()}` : item.useNextFreeSlot ? 'Next verified calendar slot' : 'Awaiting schedule'}</small>
                {item.destination && <a href={item.destination} target="_blank" rel="noreferrer">OPEN DESTINATION ↗</a>}
                {item.mediaUrls.length > 0 && <small>{item.mediaUrls.length} media item{item.mediaUrls.length === 1 ? '' : 's'} attached</small>}
                {item.publicUrl && <a href={item.publicUrl} target="_blank" rel="noreferrer">OPEN PUBLISHED POST ↗</a>}
                {item.error && <p className="marketing-error">{item.error}</p>}
              </article>
            ))}
          </div>
          <div>
            <span className="marketing-label">ANALYTICS AGENT</span>
            {data.measurements.length === 0 ? <p className="marketing-empty">Evidence windows begin after publication.</p> : data.measurements.map(item => (
              <article className="marketing-operation" key={item.id}>
                <div><b>{item.window} EVIDENCE</b><span className={`badge ${item.status === 'complete' ? 'ACTIVE' : item.status === 'due' ? 'BLOCKED' : 'IDLE'}`}>{item.status.toUpperCase()}</span></div>
                <small>Due {new Date(item.dueAt).toLocaleString()}</small>
                {item.status === 'complete' && <p>{item.impressions ?? 0} impressions · {item.engagements ?? 0} engagements · {item.clicks ?? 0} clicks · {item.destinationSessions ?? 0} destination sessions</p>}
                {item.evidenceUrl && <a href={item.evidenceUrl} target="_blank" rel="noreferrer">OPEN VERIFIED EVIDENCE ↗</a>}
              </article>
            ))}
          </div>
          <div>
            <span className="marketing-label">LEARNING AGENT</span>
            {data.learning.length === 0 ? <p className="marketing-empty">Learning reports begin after publication.</p> : data.learning.map(item => (
              <article className="marketing-operation" key={item.publicationId}>
                <div><b>{item.status.replace('-', ' ').toUpperCase()}</b></div>
                <p>{item.summary}</p>
                <small>{item.recommendation}</small>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
