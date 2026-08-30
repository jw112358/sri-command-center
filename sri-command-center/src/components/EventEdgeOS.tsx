import { FormEvent, useEffect, useMemo, useState } from 'react';
import type { EventEdgeDashboard, EventEdgePaperTrade, EventEdgeSignal } from '../types';
import { getEventEdgeDashboard, onOperatorSessionChanged, recordEventEdgeManualTrade } from '../api/client';

const familyLabel = (family: string) => ({
  btc_15m: 'BTC 15m',
  mlb_kalshi_game: 'MLB Kalshi Game',
}[family] ?? family.replace(/_/g, ' ').toUpperCase());

const sourceLaneLabel = (lane: string) => ({
  internal_btc: 'INTERNAL BTC',
  polymarket_copy: 'POLYMARKET COPY',
  unknown: 'SOURCE UNAVAILABLE',
}[lane] ?? 'SOURCE UNAVAILABLE');

const localTime = (value: string) => value
  ? new Date(value).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
  : 'n/a';

function Countdown({ expiresAt }: { expiresAt: string }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const remaining = new Date(expiresAt).getTime() - now;
  if (!expiresAt || Number.isNaN(remaining)) return <span>Settlement time unavailable</span>;
  if (remaining <= 0) return <span className="edge-expired">Settlement window ended</span>;
  const seconds = Math.floor(remaining / 1000);
  const minutes = Math.floor(seconds / 60);
  return <span>{minutes}:{String(seconds % 60).padStart(2, '0')} remaining</span>;
}

function PaperTradeCard({ trade }: { trade: EventEdgePaperTrade }) {
  const name = trade.eventTitle || trade.marketTicker || trade.eventTicker;
  const position = [trade.team, trade.side].filter(Boolean).join(' ');
  return (
    <article className="edge-position">
      <div className="edge-position-head">
        <span>{familyLabel(trade.family)}</span>
        <span className="badge IDLE">PAPER #{String(trade.sequence).padStart(3, '0')}</span>
      </div>
      <strong>{position} @ {trade.entryPrice.toFixed(4)}</strong>
      <p>{name}</p>
      <div className="edge-position-meta">
        <span>Entered {localTime(trade.enteredAt)}</span>
        <span>Expires {localTime(trade.expiresAt)}</span>
        <Countdown expiresAt={trade.expiresAt} />
      </div>
    </article>
  );
}

interface ManualForm {
  signalId: string;
  family: string;
  venue: string;
  marketTicker: string;
  side: string;
  entryPrice: string;
  quantity: string;
  cashAmount: string;
  notes: string;
}

const emptyForm = (family = 'btc_15m'): ManualForm => ({
  signalId: '', family, venue: 'kalshi', marketTicker: '', side: 'YES',
  entryPrice: '', quantity: '1', cashAmount: '', notes: '',
});

export function EventEdgeOS() {
  const [data, setData] = useState<EventEdgeDashboard | null>(null);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  const [signalScope, setSignalScope] = useState<'active' | 'all'>('active');
  const [form, setForm] = useState<ManualForm>(() => emptyForm());

  const refresh = () => getEventEdgeDashboard().then(value => {
    setData(value);
    setError('');
    setForm(current => current.marketTicker ? current : { ...current, family: value.marketFamilies[0] ?? 'btc_15m' });
  }).catch(() => setError('Sign in to load the private Event Edge operator surface.'));

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 30000);
    const unsubscribe = onOperatorSessionChanged(refresh);
    return () => { window.clearInterval(timer); unsubscribe(); };
  }, []);

  const signals = useMemo(() => {
    if (!data) return [];
    return signalScope === 'active' ? data.signals.filter(item => item.status === 'active') : data.signals;
  }, [data, signalScope]);

  const selectSignal = (signal: EventEdgeSignal) => {
    setForm({
      signalId: signal.id,
      family: signal.family,
      venue: signal.venue,
      marketTicker: signal.marketTicker,
      side: signal.side,
      entryPrice: String(signal.entryPrice),
      quantity: '1',
      cashAmount: '',
      notes: `Signal observed ${localTime(signal.observedAt)}; quoted maximum ${signal.maxAcceptablePrice ?? 'not provided'}.`,
    });
    document.getElementById('event-edge-manual-entry')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setNotice('');
    recordEventEdgeManualTrade({
      signalId: form.signalId || null,
      family: form.family,
      venue: form.venue,
      marketTicker: form.marketTicker,
      side: form.side,
      entryPrice: Number(form.entryPrice),
      quantity: form.quantity ? Number(form.quantity) : null,
      cashAmount: form.cashAmount ? Number(form.cashAmount) : null,
      notes: form.notes,
    }).then(() => {
      setNotice('Manual trade recorded. No order was transmitted by SRI Command Center.');
      setForm(emptyForm(form.family));
      return refresh();
    }).catch((reason: Error) => {
      setError(reason.message || 'The manual trade record could not be saved.');
    }).finally(() => setSaving(false));
  };

  if (!data) return <section className="event-edge-os"><div className="panel edge-empty">{error || 'LOADING EVENT EDGE OS…'}</div></section>;
  const m = data.metrics;
  const automation = data.automation;

  return (
    <section className="event-edge-os" aria-label="Event Edge operator surface">
      <div className="panel brackets edge-command-bar">
        <div>
          <span className="edge-kicker">EVENT EDGE OS · PAPER INTELLIGENCE</span>
          <strong>Signals first. Manual execution remains outside this system.</strong>
        </div>
        <div className={`edge-source edge-source-${data.sourceStatus}`}>
          <span>{data.sourceStatus.toUpperCase()}</span>
          <small>{data.sourceDetail}</small>
        </div>
        <button className="btn sm" onClick={refresh}>REFRESH</button>
      </div>

      {error && <div className="edge-warning" role="alert">{error} Last known data remains visible.</div>}
      <div className={`edge-safety ${data.liveExecutionEnabled ? 'edge-safety-live' : ''}`}>
        {data.liveExecutionEnabled
          ? 'OWNER-ONLY LIVE EXECUTION · AUTONOMOUS ORDERS INSIDE APPROVED RISK ENVELOPE'
          : 'PAPER TRADING ONLY · LIVE EXECUTION DISABLED · MANUAL ENTRIES ARE RECORDS, NOT ORDERS'}
      </div>

      <div className="panel edge-automation" aria-label="Autonomous agent safety state">
        <div className="edge-automation-state">
          <span className={`badge ${automation.heartbeatStatus === 'healthy' ? 'ACTIVE' : automation.heartbeatStatus === 'stale' ? 'IDLE' : 'BLOCKED'}`}>
            AGENT {automation.heartbeatStatus.toUpperCase()}
          </span>
          <strong>{automation.mode.toUpperCase()} MODE</strong>
          <small>Last heartbeat: {localTime(automation.lastHeartbeatAt ?? '')}</small>
          <p>{automation.detail}</p>
        </div>
        <div className="edge-control-state">
          <span>CONTROL PLANE {automation.controlPlaneConnected ? 'CONNECTED' : 'DISCONNECTED'}</span>
          <span>ORDERS {automation.ordersEnabled ? 'ENABLED' : 'BLOCKED'}</span>
          <span>PAUSE {automation.paused ? 'ENGAGED' : 'CLEAR'}</span>
          <span>KILL SWITCH {automation.killSwitchEngaged ? 'ENGAGED' : 'CLEAR'}</span>
        </div>
        <div className="edge-control-actions">
          <button className="btn sm" type="button" disabled title="Control-plane command endpoint is not connected">PAUSE AGENT</button>
          <button className="btn sm danger" type="button" disabled title="Control-plane command endpoint is not connected">KILL EXECUTION</button>
          <small>Controls fail closed until the canonical Event Edge command contract is connected and authenticated.</small>
        </div>
      </div>

      <div className="edge-metrics" aria-label="BTC paper performance summary">
        <div><span>SETTLED</span><strong>{m.settled}</strong></div>
        <div><span>OPEN PAPER</span><strong>{data.currentPaperTrades.length}</strong></div>
        <div><span>WIN RATE</span><strong>{(m.winRate * 100).toFixed(1)}%</strong></div>
        <div><span>NORMALIZED NET</span><strong className={m.normalizedNet >= 0 ? 'positive' : 'negative'}>{m.normalizedNet >= 0 ? '+' : ''}{m.normalizedNet.toFixed(4)}</strong></div>
        <div><span>MAX DRAWDOWN</span><strong>{m.maxDrawdown.toFixed(4)}</strong></div>
      </div>

      <div className="edge-primary-grid">
        <div className="panel edge-signals-panel">
          <div className="panel-h"><span className="blip"></span><span className="t">TRADE SIGNALS</span><span className="corner">30-SECOND REFRESH</span></div>
          <div className="edge-panel-controls">
            <button className={`btn sm ${signalScope === 'active' ? 'solid' : ''}`} onClick={() => setSignalScope('active')}>ACTIVE</button>
            <button className={`btn sm ${signalScope === 'all' ? 'solid' : ''}`} onClick={() => setSignalScope('all')}>RECENT</button>
          </div>
          <div className="edge-signal-list">
            {signals.length === 0 && <div className="edge-empty">{signalScope === 'active' ? 'No active signal is inside its execution window.' : 'No signal records are available yet. The feed will populate after the next upgraded supervisor refresh.'}</div>}
            {signals.map(signal => (
              <article className={`edge-signal edge-signal-${signal.status}`} key={signal.id}>
                <div className="edge-signal-head">
                  <div><span>{familyLabel(signal.family)}</span><strong>{signal.marketTicker}</strong></div>
                  <span className={`badge ${signal.status === 'active' ? 'ACTIVE' : signal.status === 'blocked' ? 'BLOCKED' : 'IDLE'}`}>{signal.status.toUpperCase()}</span>
                </div>
                <div className="edge-signal-price"><strong>{signal.side} @ {signal.entryPrice.toFixed(4)}</strong><span>Max {signal.maxAcceptablePrice?.toFixed(4) ?? 'n/a'}</span></div>
                <div className="edge-signal-attribution">
                  <span>{sourceLaneLabel(signal.sourceLane)}</span>
                  <span>{signal.lifecycleStatus.replace(/_/g, ' ').toUpperCase()}</span>
                  {signal.sourceTrader && <span>TRADER {signal.sourceTrader}</span>}
                </div>
                <p>{signal.primarySignal || signal.supportingSignals || 'Signal context is available in the Event Edge research packet.'}</p>
                {signal.rejectionReason && <p className="edge-rejection">Rejected: {signal.rejectionReason}</p>}
                <div className="edge-signal-foot"><span>{localTime(signal.observedAt)}</span><span>{localTime(signal.expiresAt)}</span></div>
                {signal.status === 'active' && <button className="btn solid sm" onClick={() => selectSignal(signal)}>USE SIGNAL FOR MANUAL ENTRY</button>}
              </article>
            ))}
          </div>
        </div>

        <div className="panel edge-current-panel">
          <div className="panel-h"><span className="t">CURRENT PAPER TRADES</span><span className="corner">SUPERVISOR LEDGER</span></div>
          <div className="edge-position-list">
            {data.currentPaperTrades.length === 0
              ? <div className="edge-empty">No active paper position. The paper supervisor continues scanning.</div>
              : data.currentPaperTrades.map(trade => <PaperTradeCard trade={trade} key={trade.id} />)}
          </div>
        </div>
      </div>

      <div className="edge-secondary-grid">
        <form className="panel edge-entry" id="event-edge-manual-entry" onSubmit={submit}>
          <div className="panel-h"><span className="t">RECORD MANUAL TRADE</span><span className="corner">EXTERNAL EXECUTION ONLY</span></div>
          <div className="edge-form-grid">
            <label>MARKET FAMILY<select value={form.family} onChange={e => setForm({ ...form, family: e.target.value })}>{data.marketFamilies.map(family => <option value={family} key={family}>{familyLabel(family)}</option>)}</select></label>
            <label>VENUE<input value={form.venue} onChange={e => setForm({ ...form, venue: e.target.value })} required /></label>
            <label className="wide">MARKET / CONTRACT<input value={form.marketTicker} onChange={e => setForm({ ...form, marketTicker: e.target.value })} required /></label>
            <label>SIDE<select value={form.side} onChange={e => setForm({ ...form, side: e.target.value })}><option>YES</option><option>NO</option><option>BUY</option><option>SELL</option></select></label>
            <label>ENTRY PRICE<input type="number" min="0.0001" step="0.0001" value={form.entryPrice} onChange={e => setForm({ ...form, entryPrice: e.target.value })} required /></label>
            <label>QUANTITY<input type="number" min="0.0001" step="0.0001" value={form.quantity} onChange={e => setForm({ ...form, quantity: e.target.value })} /></label>
            <label>CASH AMOUNT<input type="number" min="0.01" step="0.01" value={form.cashAmount} onChange={e => setForm({ ...form, cashAmount: e.target.value })} /></label>
            <label className="wide">NOTES<textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} /></label>
          </div>
          <div className="edge-entry-actions"><span>{form.signalId ? `LINKED SIGNAL: ${form.signalId}` : 'UNLINKED OPERATOR ENTRY'}</span><button className="btn solid" disabled={saving}>{saving ? 'RECORDING…' : 'RECORD MANUAL TRADE'}</button></div>
          {notice && <p className="edge-success" role="status">{notice}</p>}
        </form>

        <div className="panel edge-manual-ledger">
          <div className="panel-h"><span className="t">MANUAL ENTRY LEDGER</span><span className="corner">{data.manualTrades.length} RECORDS</span></div>
          <div className="edge-table-wrap">
            <table><thead><tr><th>TIME</th><th>FAMILY</th><th>CONTRACT</th><th>POSITION</th><th>SIZE</th></tr></thead><tbody>
              {data.manualTrades.length === 0 && <tr><td colSpan={5}>No manual entries recorded.</td></tr>}
              {data.manualTrades.map(trade => <tr key={trade.id}><td>{localTime(trade.enteredAt)}</td><td>{familyLabel(trade.family)}</td><td>{trade.marketTicker}</td><td>{trade.side} @ {trade.entryPrice.toFixed(4)}</td><td>{trade.quantity ? `${trade.quantity} units` : `$${trade.cashAmount?.toFixed(2)}`}</td></tr>)}
            </tbody></table>
          </div>
        </div>
      </div>

      <div className="panel edge-executions">
        <div className="panel-h"><span className="t">EXECUTION LIFECYCLE</span><span className="corner">{data.executionRecords.length} RECORDS</span></div>
        <div className="edge-table-wrap">
          <table><thead><tr><th>UPDATED</th><th>MODE</th><th>SOURCE</th><th>CONTRACT</th><th>STATUS</th><th>FILL</th><th>FEES</th><th>REALIZED P&amp;L</th></tr></thead><tbody>
            {data.executionRecords.length === 0 && <tr><td colSpan={8}>No execution records are available. Live trading remains blocked unless a healthy authenticated control plane supplies them.</td></tr>}
            {data.executionRecords.map(record => <tr key={record.id}>
              <td>{localTime(record.updatedAt)}</td>
              <td><span className={`badge ${record.executionMode === 'live' ? 'BLOCKED' : 'IDLE'}`}>{record.executionMode.toUpperCase()}</span></td>
              <td>{sourceLaneLabel(record.sourceLane)}{record.sourceTrader ? ` · ${record.sourceTrader}` : ''}</td>
              <td>{record.marketTicker}<br />{record.side}</td>
              <td>{record.lifecycleStatus.replace(/_/g, ' ').toUpperCase()}{record.rejectionReason ? <><br /><span className="negative">{record.rejectionReason}</span></> : null}</td>
              <td>{record.filledContracts}/{record.requestedContracts}{record.averageFillPrice != null ? ` @ ${record.averageFillPrice.toFixed(4)}` : ''}</td>
              <td>{record.fees == null ? 'pending' : `$${record.fees.toFixed(4)}`}</td>
              <td className={(record.realizedPnl ?? 0) >= 0 ? 'positive' : 'negative'}>{record.realizedPnl == null ? 'pending' : `${record.realizedPnl >= 0 ? '+' : ''}$${record.realizedPnl.toFixed(4)}`}</td>
            </tr>)}
          </tbody></table>
        </div>
      </div>

      <div className="panel edge-history">
        <div className="panel-h"><span className="t">RECENT PAPER RESULTS</span><span className="corner">LATEST {data.recentPaperTrades.length}</span></div>
        <div className="edge-table-wrap">
          <table><thead><tr><th>#</th><th>FAMILY</th><th>CONTRACT</th><th>POSITION</th><th>OUTCOME</th><th>NET</th><th>STRATEGY</th></tr></thead><tbody>
            {data.recentPaperTrades.map(trade => <tr key={trade.id}><td>{String(trade.sequence).padStart(3, '0')}</td><td>{familyLabel(trade.family)}</td><td>{trade.eventTitle || trade.marketTicker}</td><td>{trade.team} {trade.side} @ {trade.entryPrice.toFixed(4)}</td><td><span className={`badge ${trade.outcome === 'win' ? 'ACTIVE' : trade.outcome === 'loss' ? 'BLOCKED' : 'IDLE'}`}>{trade.outcome.toUpperCase()}</span></td><td className={trade.netResult >= 0 ? 'positive' : 'negative'}>{trade.netResult >= 0 ? '+' : ''}{trade.netResult.toFixed(4)}</td><td>{trade.strategy}</td></tr>)}
          </tbody></table>
        </div>
      </div>
    </section>
  );
}
