import { useEffect, useState } from 'react';
import { getLegalDashboard } from '../api/client';
import type { LegalConnectorStatus, LegalDashboardState } from '../types';

type LegalView = 'overview' | 'matters' | 'intake' | 'review';

interface LegalAgentOSProps {
  apiConnected: boolean;
}

const WORKFLOW = [
  { number: '01', label: 'INTAKE', detail: 'Email or manual', state: 'ready' },
  { number: '02', label: 'VALIDATE', detail: 'Scope + deadlines', state: 'next' },
  { number: '03', label: 'RESEARCH', detail: 'Authority + record', state: 'next' },
  { number: '04', label: 'DRAFT', detail: 'SC civil / appeal', state: 'next' },
  { number: '05', label: 'QUALITY', detail: 'Citations + risks', state: 'next' },
  { number: '06', label: 'APPROVE', detail: 'Jeff exclusively', state: 'gate' },
  { number: '07', label: 'DELIVER', detail: 'External action', state: 'gate' },
] as const;

const CONNECTORS: LegalConnectorStatus[] = [
  { name: 'GMAIL', detail: 'LegalOS/Intake', status: 'READY' },
  { name: 'DRIVE', detail: 'Matter system of record', status: 'READY' },
  { name: 'CALENDAR', detail: 'Tentative deadlines', status: 'READY' },
  { name: 'MIDPAGE', detail: 'Research + cite-check', status: 'READY' },
  { name: 'DESCRYBE', detail: 'Secondary legal research', status: 'READY' },
  { name: 'AUTOMATION', detail: 'Scanner + matter runner', status: 'STAGED' },
] as const;

export function LegalAgentOS({ apiConnected }: LegalAgentOSProps) {
  const [view, setView] = useState<LegalView>('overview');
  const [requestType, setRequestType] = useState('NEW MATTER');
  const [dashboard, setDashboard] = useState<LegalDashboardState | null>(null);

  useEffect(() => {
    let mounted = true;
    getLegalDashboard().then(state => {
      if (mounted && state) setDashboard(state);
    });
    const interval = window.setInterval(() => {
      getLegalDashboard().then(state => {
        if (mounted && state) setDashboard(state);
      });
    }, 30_000);
    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, []);

  const activeCount = dashboard?.activeCount ?? 0;
  const capacity = dashboard?.capacity ?? 4;
  const awaitingApproval = dashboard?.awaitingApproval ?? 0;
  const upcomingDeadlines = dashboard?.upcomingDeadlines ?? 0;
  const matters = dashboard?.matters ?? [];
  const connectors = dashboard?.connectors ?? CONNECTORS;
  const readyConnectors = connectors.filter(connector => connector.status === 'READY').length;

  return (
    <section className="laos" aria-label="Legal Agent OS">
      <div className="laos-hero">
        <div>
          <div className="laos-kicker">SRI INTELLIGENCE · SOUTH CAROLINA</div>
          <h1>LEGAL AGENT OS</h1>
          <p>
            Civil litigation and appeals—from intake signal to approved work product.
            Research and drafting run autonomously; every external action stops for Jeff.
          </p>
        </div>
        <div className="laos-hero-status">
          <span className="badge ACTIVE"><span className="bd"></span>CONTROL LAYER READY</span>
          <span className={'badge ' + (apiConnected ? 'ACTIVE' : 'IDLE')}>
            <span className="bd"></span>
            {apiConnected ? 'PLATFORM CONNECTED' : 'LIVE MATTER FEED STAGED'}
          </span>
        </div>
      </div>

      <nav className="laos-nav" aria-label="Legal Agent OS sections">
        {([
          ['overview', '01 OVERVIEW'],
          ['matters', '02 MATTERS'],
          ['intake', '03 INTAKE'],
          ['review', '04 REVIEW + DELIVERY'],
        ] as const).map(([id, label]) => (
          <button
            key={id}
            className={view === id ? 'active' : ''}
            onClick={() => setView(id)}
            type="button"
          >
            {label}
          </button>
        ))}
      </nav>

      {(view === 'overview' || view === 'matters') && (
        <>
          <div className="laos-metrics">
            <article className="panel laos-metric">
              <span className="laos-label">ACTIVE MATTERS</span>
              <strong>{activeCount} <small>/ {capacity}</small></strong>
              <div className="laos-capacity" aria-label="Four available matter slots">
                <i></i><i></i><i></i><i></i>
              </div>
              <em>{capacity - activeCount} WORK SLOTS AVAILABLE</em>
            </article>
            <article className="panel laos-metric">
              <span className="laos-label">AWAITING APPROVAL</span>
              <strong>{awaitingApproval}</strong>
              <em>{awaitingApproval ? 'DECISIONS REQUIRE REVIEW' : 'NO DECISIONS PENDING'}</em>
            </article>
            <article className="panel laos-metric">
              <span className="laos-label">DEADLINES · 30 DAYS</span>
              <strong>{upcomingDeadlines}</strong>
              <em>TENTATIVE UNTIL CONFIRMED</em>
            </article>
            <article className="panel laos-metric">
              <span className="laos-label">SYSTEM READINESS</span>
              <strong>{readyConnectors} <small>/ {connectors.length}</small></strong>
              <em>AUTOMATION RUNNER NEXT</em>
            </article>
          </div>

          <div className="laos-main-grid">
            <article className="panel laos-matters">
              <div className="panel-h">
                <span className="t">ACTIVE MATTERS</span>
                <span className="corner">CAPACITY 4 · CONCURRENCY 4</span>
              </div>
              {matters.length === 0 ? (
                <div className="laos-empty">
                  <span className="laos-empty-count">00</span>
                  <div>
                    <strong>NO MATTERS ARE RUNNING</strong>
                    <p>
                      Apply <code>LegalOS/Intake</code> in Gmail or enter a request here.
                      Revisions, strategy memos, and standalone research use the same route.
                    </p>
                    <button className="btn solid" type="button" onClick={() => setView('intake')}>
                      + OPEN MANUAL INTAKE
                    </button>
                  </div>
                </div>
              ) : (
                <div className="laos-matter-list">
                  {matters.map(matter => (
                    <div className="laos-matter-row" key={matter.matterId}>
                      <span>
                        <strong>{matter.displayName}</strong>
                        <small>{matter.matterId} · V{matter.version} · {matter.practiceLane.toUpperCase()}</small>
                      </span>
                      <em>{matter.requestType.replace(/_/g, ' ').toUpperCase()}</em>
                      <span className={'badge ' + (matter.status === 'blocked' ? 'BLOCKED' : 'IDLE')}>
                        <span className="bd"></span>
                        {matter.status.replace(/_/g, ' ').toUpperCase()}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </article>

            <article className="panel laos-approval">
              <div className="panel-h">
                <span className="t">APPROVAL CONTROL</span>
                <span className="badge BLOCKED"><span className="bd"></span>LOCKED</span>
              </div>
              <div className="laos-rules">
                <div><b>A</b><span><strong>PREPARE AUTONOMOUSLY</strong><small>Research, drafts, QA, redlines, review packets.</small></span></div>
                <div><b>B</b><span><strong>JEFF REVIEWS</strong><small>One approval owner for every matter and output.</small></span></div>
                <div><b>C</b><span><strong>EXTERNAL ACTIONS STOP</strong><small>Email, delivery, filing, and sends require approval.</small></span></div>
              </div>
              <div className="laos-stop">
                <span><strong>EMERGENCY PAUSE</strong><small>Stops new pipeline work.</small></span>
                <button className="btn danger" disabled type="button">AVAILABLE WITH RUNNER</button>
              </div>
            </article>
          </div>

          <article className="panel laos-workflow">
            <div className="panel-h">
              <span className="t">MATTER PIPELINE</span>
              <span className="corner">SC CIVIL · APPEAL</span>
            </div>
            <div className="laos-workflow-steps">
              {WORKFLOW.map(step => (
                <div className={'laos-step ' + step.state} key={step.number}>
                  <span>{step.number}</span>
                  <strong>{step.label}</strong>
                  <small>{step.detail}</small>
                </div>
              ))}
            </div>
          </article>
        </>
      )}

      {(view === 'overview' || view === 'intake') && (
        <div className="laos-lower-grid">
          <article className="panel">
            <div className="panel-h">
              <span className="t">INTAKE CHANNELS</span>
              <span className="corner">AUTO-MATCH REVISIONS</span>
            </div>
            <div className="laos-channel">
              <b>G</b>
              <span><strong>GMAIL SCANNER</strong><small>jeff@sri-intel.com · LegalOS/Intake</small></span>
              <em>LABEL READY</em>
            </div>
            <div className="laos-channel">
              <b>M</b>
              <span><strong>MASTER BUILDER</strong><small>New matter, revision, memo, or research</small></span>
              <em>READY NOW</em>
            </div>
            <div className="laos-notice-policy">
              <span>RECEIPT ACKNOWLEDGEMENT <strong>DRAFT FOR APPROVAL</strong></span>
              <span>COMPLETION NOTICE <strong>DRAFT FOR APPROVAL</strong></span>
            </div>
          </article>

          <article className="panel laos-intake-form">
            <div className="panel-h">
              <span className="t">MANUAL INTAKE</span>
              <span className="corner">CONTROLLED ENTRY</span>
            </div>
            <div className="laos-form-body">
              <label>
                REQUEST TYPE
                <select value={requestType} onChange={e => setRequestType(e.target.value)}>
                  <option>NEW MATTER</option>
                  <option>REVISION REQUEST</option>
                  <option>STRATEGY MEMO</option>
                  <option>LEGAL RESEARCH</option>
                </select>
              </label>
              <label>
                MATTER / REQUEST
                <textarea placeholder="Identify the parties, request, known deadlines, objectives, and any workflow notes…" />
              </label>
              <div className="laos-form-action">
                <small>Saves to Drive and begins validation when the automation runner is connected.</small>
                <button className="btn solid" disabled type="button">SUBMIT INTAKE · STAGED</button>
              </div>
            </div>
          </article>
        </div>
      )}

      {(view === 'overview' || view === 'review') && (
        <div className="laos-lower-grid">
          <article className="panel">
            <div className="panel-h">
              <span className="t">REVIEW + DELIVERY</span>
              <span className="corner">0 PACKETS</span>
            </div>
            <div className="laos-review-empty">
              <span>QA</span>
              <div>
                <strong>NOTHING NEEDS YOUR DECISION</strong>
                <p>Completed work appears here with the source record, draft, authorities, citation findings, risk flags, and exact proposed external action.</p>
              </div>
            </div>
          </article>

          <article className="panel">
            <div className="panel-h">
              <span className="t">CONNECTOR READINESS</span>
              <span className="corner">5 READY · 1 STAGED</span>
            </div>
            <div className="laos-connectors">
              {connectors.map(connector => (
                <div key={connector.name}>
                  <span className={'laos-connector-dot ' + connector.status.toLowerCase()}></span>
                  <strong>{connector.name}</strong>
                  <small>{connector.detail}</small>
                  <em>{connector.status}</em>
                </div>
              ))}
            </div>
          </article>
        </div>
      )}
    </section>
  );
}
