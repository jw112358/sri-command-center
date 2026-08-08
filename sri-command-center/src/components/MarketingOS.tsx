import { useEffect, useState } from 'react';
import type { MarketingDashboard } from '../types';
import { getMarketingDashboard, onOperatorSessionChanged, setMarketingApproval } from '../api/client';

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
    return onOperatorSessionChanged(refresh);
  }, []);

  const approve = (id: string, approved: boolean) => {
    setSaving(id);
    setMarketingApproval(id, approved).then(value => {
      setData(value);
      setError('');
    }).catch(() => setError('The approval could not be saved.')).finally(() => setSaving(''));
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
                <div className="marketing-actions">
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
            <div className="marketing-measure"><span className="marketing-label">MEASUREMENT SOURCE</span><p>{data.measurementSource}</p></div>
            {error && <p className="marketing-error">{error}</p>}
          </div>
        </div>
      </div>
    </section>
  );
}
