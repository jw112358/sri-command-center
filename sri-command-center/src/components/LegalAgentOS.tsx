import { useEffect, useRef, useState } from 'react';
import {
  clearLegalOperatorSession,
  getLegalAuthConfig,
  getLegalDashboard,
  getLegalOperatorSession,
  pauseLegalOS,
  resumeLegalOS,
  signInLegalOperator,
  submitLegalIntake,
} from '../api/client';
import type {
  LegalAuthConfig,
  LegalConnectorStatus,
  LegalDashboardState,
  LegalRequestType,
  LegalSessionStatus,
} from '../types';

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

let googleIdentityPromise: Promise<void> | null = null;

function loadGoogleIdentity(): Promise<void> {
  if (window.google?.accounts.id) return Promise.resolve();
  if (googleIdentityPromise) return googleIdentityPromise;
  googleIdentityPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      'script[src="https://accounts.google.com/gsi/client"]',
    );
    const script = existing ?? document.createElement('script');
    const onReady = () => window.google?.accounts.id
      ? resolve()
      : reject(new Error('Google Identity Services did not initialize'));
    script.addEventListener('load', onReady, { once: true });
    script.addEventListener('error', () => reject(new Error('Google sign-in failed to load')), {
      once: true,
    });
    if (!existing) {
      script.src = 'https://accounts.google.com/gsi/client';
      script.async = true;
      script.defer = true;
      document.head.appendChild(script);
    }
  });
  return googleIdentityPromise;
}

export function LegalAgentOS({ apiConnected }: LegalAgentOSProps) {
  const [view, setView] = useState<LegalView>('overview');
  const [requestType, setRequestType] = useState<LegalRequestType>('new_matter');
  const [practiceLane, setPracticeLane] = useState<'civil' | 'appeal'>('civil');
  const [requestBody, setRequestBody] = useState('');
  const [dashboard, setDashboard] = useState<LegalDashboardState | null>(null);
  const [authConfig, setAuthConfig] = useState<LegalAuthConfig | null>(null);
  const [operatorSession, setOperatorSession] = useState<LegalSessionStatus | null>(null);
  const [operatorBusy, setOperatorBusy] = useState(false);
  const [operatorMessage, setOperatorMessage] = useState('');
  const googleButtonRef = useRef<HTMLDivElement>(null);

  const refreshDashboard = () => {
    getLegalDashboard().then(state => {
      if (state) setDashboard(state);
    });
  };

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

  useEffect(() => {
    let mounted = true;
    Promise.all([getLegalAuthConfig(), getLegalOperatorSession()]).then(
      ([config, session]) => {
        if (!mounted) return;
        setAuthConfig(config);
        setOperatorSession(session);
      },
    );
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    if (!authConfig?.enabled || operatorSession || !googleButtonRef.current) return;
    let active = true;
    loadGoogleIdentity()
      .then(() => {
        if (!active || !window.google || !googleButtonRef.current) return;
        googleButtonRef.current.replaceChildren();
        window.google.accounts.id.initialize({
          client_id: authConfig.clientId,
          hd: 'sri-intel.com',
          callback: async response => {
            setOperatorBusy(true);
            setOperatorMessage('');
            try {
              await signInLegalOperator(response.credential);
              const session = await getLegalOperatorSession();
              setOperatorSession(session);
              setOperatorMessage('Jeff-only controls unlocked for this browser session.');
            } catch (error) {
              setOperatorMessage(error instanceof Error ? error.message : 'Google sign-in failed.');
            } finally {
              setOperatorBusy(false);
            }
          },
        });
        window.google.accounts.id.renderButton(googleButtonRef.current, {
          theme: 'outline',
          size: 'medium',
          shape: 'rectangular',
          text: 'signin_with',
          width: 220,
        });
      })
      .catch(error => {
        if (active) {
          setOperatorMessage(error instanceof Error ? error.message : 'Google sign-in failed.');
        }
      });
    return () => { active = false; };
  }, [authConfig, operatorSession]);

  const handlePause = async () => {
    if (!operatorSession) return;
    setOperatorBusy(true);
    setOperatorMessage('');
    try {
      const next = dashboard?.paused ? await resumeLegalOS() : await pauseLegalOS();
      setDashboard(current => current ? { ...current, paused: next.paused } : current);
      setOperatorMessage(next.paused ? 'New pipeline work is paused.' : 'Pipeline intake is resumed.');
    } catch (error) {
      setOperatorMessage(error instanceof Error ? error.message : 'Control request failed.');
    } finally {
      setOperatorBusy(false);
    }
  };

  const handleSignOut = () => {
    clearLegalOperatorSession();
    window.google?.accounts.id.disableAutoSelect();
    setOperatorSession(null);
    setOperatorMessage('Operator session closed.');
  };

  const handleManualIntake = async () => {
    if (!operatorSession || !authConfig?.manualIntakeEnabled || !requestBody.trim()) return;
    setOperatorBusy(true);
    setOperatorMessage('');
    try {
      const receipt = await submitLegalIntake({
        requestType,
        practiceLane,
        body: requestBody.trim(),
      });
      setRequestBody('');
      refreshDashboard();
      setOperatorMessage(
        `${receipt.matter.matterId} received. Acknowledgement remains pending approval.`,
      );
    } catch (error) {
      setOperatorMessage(error instanceof Error ? error.message : 'Manual intake failed.');
    } finally {
      setOperatorBusy(false);
    }
  };

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

      <div className="laos-auth-strip">
        <span>
          <strong>OPERATOR ACCESS</strong>
          <small>
            {operatorSession
              ? `${operatorSession.email} · session expires ${new Date(operatorSession.expiresAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`
              : authConfig?.enabled
                ? 'Sign in with the authorized SRI Google Workspace account.'
                : 'Google Workspace authentication is staged for configuration.'}
          </small>
        </span>
        {operatorSession ? (
          <button className="btn" type="button" onClick={handleSignOut}>SIGN OUT</button>
        ) : authConfig?.enabled ? (
          <div className="laos-google-button" ref={googleButtonRef} aria-busy={operatorBusy}></div>
        ) : (
          <em>SETUP REQUIRED</em>
        )}
        {operatorMessage && <p>{operatorMessage}</p>}
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
                <button
                  className="btn danger"
                  disabled={!operatorSession || operatorBusy}
                  onClick={handlePause}
                  type="button"
                >
                  {dashboard?.paused ? 'RESUME PIPELINE' : 'PAUSE NEW WORK'}
                </button>
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
                <select
                  value={requestType}
                  onChange={e => setRequestType(e.target.value as LegalRequestType)}
                >
                  <option value="new_matter">NEW MATTER</option>
                  <option value="revision">REVISION REQUEST</option>
                  <option value="strategy_memo">STRATEGY MEMO</option>
                  <option value="standalone_research">LEGAL RESEARCH</option>
                </select>
              </label>
              <label>
                PRACTICE LANE
                <select
                  value={practiceLane}
                  onChange={e => setPracticeLane(e.target.value as 'civil' | 'appeal')}
                >
                  <option value="civil">SC CIVIL</option>
                  <option value="appeal">SC APPEAL</option>
                </select>
              </label>
              <label>
                MATTER / REQUEST
                <textarea
                  value={requestBody}
                  onChange={e => setRequestBody(e.target.value)}
                  placeholder="Identify the parties, request, known deadlines, objectives, and any workflow notes…"
                />
              </label>
              <div className="laos-form-action">
                <small>
                  {!operatorSession
                    ? 'Jeff-only Google sign-in is required.'
                    : !authConfig?.manualIntakeEnabled
                      ? 'Persistent state and Drive-first intake must be enabled before submission.'
                      : 'Creates a controlled intake event; no external action occurs.'}
                </small>
                <button
                  className="btn solid"
                  disabled={
                    !operatorSession
                    || !authConfig?.manualIntakeEnabled
                    || !requestBody.trim()
                    || operatorBusy
                  }
                  onClick={handleManualIntake}
                  type="button"
                >
                  {authConfig?.manualIntakeEnabled ? 'SUBMIT CONTROLLED INTAKE' : 'SUBMIT INTAKE · STAGED'}
                </button>
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
