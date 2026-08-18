import { useEffect, useRef, useState } from 'react';
import {
  clearLegalOperatorSession,
  decideLegalReviewPacket,
  getLegalAuthConfig,
  getLegalDashboard,
  getLegalOperatorSession,
  getLegalReviewPackets,
  pauseLegalOS,
  resumeLegalOS,
  resolveLegalMatterClarifications,
  signInLegalOperator,
} from '../api/client';
import type {
  LegalAuthConfig,
  LegalDashboardState,
  LegalMatterSummary,
  LegalReviewPacket,
  LegalSessionStatus,
} from '../types';
import LegalManualIntakeWorkspace from './LegalManualIntakeWorkspace';
import LegalDocumentsWorkspace from './LegalDocumentsWorkspace';

type LegalView = 'overview' | 'matters' | 'documents' | 'intake' | 'review';

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
  const [dashboard, setDashboard] = useState<LegalDashboardState | null>(null);
  const [authConfig, setAuthConfig] = useState<LegalAuthConfig | null>(null);
  const [operatorSession, setOperatorSession] = useState<LegalSessionStatus | null>(null);
  const [operatorBusy, setOperatorBusy] = useState(false);
  const [operatorMessage, setOperatorMessage] = useState('');
  const [selectedMatterId, setSelectedMatterId] = useState<string | null>(null);
  const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, string>>({});
  const [clarificationNote, setClarificationNote] = useState('');
  const [reviewPackets, setReviewPackets] = useState<LegalReviewPacket[]>([]);
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [reviewBusyId, setReviewBusyId] = useState<string | null>(null);
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
    if (!operatorSession) {
      setReviewPackets([]);
      return;
    }
    let mounted = true;
    const refresh = () => {
      getLegalReviewPackets()
        .then(packets => {
          if (mounted) setReviewPackets(packets);
        })
        .catch(error => {
          if (mounted) {
            setOperatorMessage(
              error instanceof Error ? error.message : 'Review packets could not be loaded.',
            );
          }
        });
    };
    refresh();
    const interval = window.setInterval(refresh, 30_000);
    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, [operatorSession]);

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
      setOperatorMessage(next.paused ? 'Canonical pipeline paused.' : 'Canonical pipeline resumed.');
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

  const activeCount = dashboard?.activeCount ?? 0;
  const capacity = dashboard?.capacity ?? 4;
  const awaitingApproval = dashboard?.awaitingApproval ?? 0;
  const upcomingDeadlines = dashboard?.upcomingDeadlines ?? 0;
  const matters = dashboard?.matters ?? [];
  const selectedMatter = matters.find(matter => matter.matterId === selectedMatterId) ?? null;
  const qualityReviewMatters = matters.filter(matter => matter.status === 'quality_review');
  const awaitingReviewPackets = reviewPackets.filter(packet => packet.status === 'awaiting_review');
  const connectors = dashboard?.connectors ?? [];
  const readyConnectors = connectors.filter(connector => connector.status === 'READY').length;
  const stagedConnectors = connectors.filter(connector => connector.status === 'STAGED').length;
  const gmailConnector = connectors.find(connector => connector.name === 'GMAIL');

  const selectMatter = (matter: LegalMatterSummary) => {
    setSelectedMatterId(matter.matterId);
    setClarificationAnswers(
      Object.fromEntries((matter.blockingGaps ?? []).map(gap => [gap, ''])),
    );
    setClarificationNote('');
  };

  const handleClarificationResolution = async () => {
    if (!operatorSession || !selectedMatter || selectedMatter.status !== 'needs_operator') return;
    if (selectedMatter.blockingGaps.some(gap => !clarificationAnswers[gap]?.trim())) {
      setOperatorMessage('Every listed clarification requires a response before the matter can resume.');
      return;
    }
    setOperatorBusy(true);
    setOperatorMessage('');
    try {
      const updated = await resolveLegalMatterClarifications(selectedMatter.matterId, {
        expectedVersion: selectedMatter.version,
        answers: Object.fromEntries(
          selectedMatter.blockingGaps.map(gap => [gap, clarificationAnswers[gap].trim()]),
        ),
        operatorNote: clarificationNote.trim(),
      });
      setDashboard(current => current ? {
        ...current,
        matters: current.matters.map(matter => matter.matterId === updated.matterId ? updated : matter),
      } : current);
      setOperatorMessage(`${updated.matterId} clarifications archived to private Drive; intake validation may resume.`);
    } catch (error) {
      setOperatorMessage(error instanceof Error ? error.message : 'Clarification resolution failed.');
    } finally {
      setOperatorBusy(false);
    }
  };

  const handleReviewDecision = async (
    packet: LegalReviewPacket,
    decision: 'approve' | 'request_revision' | 'reject',
  ) => {
    const note = reviewNotes[packet.packetId]?.trim() ?? '';
    if (!operatorSession || !note) {
      setOperatorMessage('Enter a decision note before approving, requesting revision, or rejecting.');
      return;
    }
    setReviewBusyId(packet.packetId);
    setOperatorMessage('');
    try {
      const updated = await decideLegalReviewPacket(packet.packetId, decision, note);
      setReviewPackets(current => current.map(item => (
        item.packetId === updated.packetId ? updated : item
      )));
      setReviewNotes(current => ({ ...current, [packet.packetId]: '' }));
      refreshDashboard();
      const result = decision === 'approve'
        ? 'approved for internal work-product completion; delivery remains locked'
        : decision === 'request_revision'
          ? 'returned to the autonomous revision pipeline'
          : 'rejected and blocked from further action';
      setOperatorMessage(`${packet.matterId} ${result}.`);
    } catch (error) {
      setOperatorMessage(error instanceof Error ? error.message : 'Review decision failed.');
    } finally {
      setReviewBusyId(null);
    }
  };

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
          <span className={'badge ' + (operatorSession ? 'ACTIVE' : 'IDLE')}>
            <span className="bd"></span>
            {operatorSession ? 'OPERATOR CONTROLS UNLOCKED' : 'OPERATOR CONTROLS LOCKED'}
          </span>
          <span className={'badge ' + (apiConnected ? 'ACTIVE' : 'IDLE')}>
            <span className="bd"></span>
            {apiConnected ? 'API CONNECTED' : 'API OFFLINE'}
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
          ['documents', '03 DOCUMENTS'],
          ['intake', '04 INTAKE'],
          ['review', '05 REVIEW + DELIVERY'],
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
                      Canonical Legal Agent OS state is connected here. Gmail scanning and the
                      complete Intake v1.1 form remain staged for controlled activation.
                    </p>
                    <button className="btn solid" type="button" onClick={() => setView('intake')}>
                      + OPEN MANUAL INTAKE
                    </button>
                  </div>
                </div>
              ) : (
                <div className="laos-matter-list">
                  {matters.map(matter => (
                    <button
                      className={'laos-matter-row' + (selectedMatterId === matter.matterId ? ' selected' : '')}
                      key={matter.matterId}
                      onClick={() => selectMatter(matter)}
                      type="button"
                    >
                      <span>
                        <strong>{matter.displayName}</strong>
                        <small>{matter.matterId} · V{matter.version} · {matter.practiceLane.toUpperCase()}</small>
                      </span>
                      <em>{matter.requestType.replace(/_/g, ' ').toUpperCase()}</em>
                      <span className={'badge ' + (matter.status === 'blocked' ? 'BLOCKED' : 'IDLE')}>
                        <span className="bd"></span>
                        {matter.status.replace(/_/g, ' ').toUpperCase()}
                      </span>
                    </button>
                  ))}
                </div>
              )}
              {selectedMatter && (
                <div className="laos-matter-detail">
                  <div className="laos-matter-detail-heading">
                    <span>
                      <strong>{selectedMatter.displayName}</strong>
                      <small>{selectedMatter.matterId} · VERSION {selectedMatter.version}</small>
                    </span>
                    <button className="secondary-button" type="button" onClick={() => setSelectedMatterId(null)}>CLOSE</button>
                  </div>
                  <p>{selectedMatter.currentSummary || 'No matter summary is available yet.'}</p>
                  <div className="laos-next-action"><span>NEXT ACTION</span>{selectedMatter.exactNextAction || 'Await the next canonical workflow update.'}</div>
                  {selectedMatter.intakeCompletenessScore != null && (
                    <div className="laos-completeness">INTAKE COMPLETENESS <strong>{selectedMatter.intakeCompletenessScore}%</strong></div>
                  )}
                  {selectedMatter.status === 'needs_operator' && selectedMatter.blockingGaps.length > 0 && (
                    <div className="laos-clarifications">
                      <strong>OPERATOR CLARIFICATIONS REQUIRED</strong>
                      <p>Responses are archived in the private Drive matter folder. MongoDB receives only the resolved field names and artifact provenance.</p>
                      {selectedMatter.blockingGaps.map(gap => (
                        <label key={gap}>
                          {gap}
                          <textarea
                            rows={3}
                            value={clarificationAnswers[gap] ?? ''}
                            onChange={event => setClarificationAnswers(current => ({ ...current, [gap]: event.target.value }))}
                          />
                        </label>
                      ))}
                      <label>
                        OPERATOR NOTE (OPTIONAL)
                        <textarea rows={3} value={clarificationNote} onChange={event => setClarificationNote(event.target.value)} />
                      </label>
                      <button className="btn solid" disabled={operatorBusy || !operatorSession} onClick={handleClarificationResolution} type="button">
                        {operatorBusy ? 'ARCHIVING…' : 'ARCHIVE RESPONSES + RESUME MATTER'}
                      </button>
                    </div>
                  )}
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
                  disabled={!operatorSession || operatorBusy || !dashboard}
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

      {view === 'documents' && (
        <div className="laos-documents-view">
          <article className="panel document-matter-picker">
            <div className="panel-h"><span className="t">SELECT MATTER</span><span className="corner">SOURCE ISOLATION REQUIRED</span></div>
            <label>
              Matter
              <select value={selectedMatterId ?? ''} onChange={event => setSelectedMatterId(event.target.value || null)}>
                <option value="">Choose a matter…</option>
                {matters.map(matter => <option value={matter.matterId} key={matter.matterId}>{matter.displayName} · {matter.matterId}</option>)}
              </select>
            </label>
          </article>
          {selectedMatterId ? <LegalDocumentsWorkspace matterId={selectedMatterId} /> : <article className="panel legal-doc-empty">Select a matter to upload, inspect, and approve its source documents.</article>}
        </div>
      )}

      {view === 'overview' && (
        <div className="laos-lower-grid">
          <article className="panel">
            <div className="panel-h">
              <span className="t">INTAKE CHANNELS</span>
              <span className="corner">AUTO-MATCH REVISIONS</span>
            </div>
            <div className="laos-channel">
              <b>G</b>
              <span><strong>GMAIL SCANNER</strong><small>jeff@sri-intel.com · LegalOS/Intake</small></span>
              <em>{gmailConnector?.status ?? 'STAGED'}</em>
            </div>
            <div className="laos-channel">
              <b>M</b>
              <span><strong>MASTER BUILDER</strong><small>New matter, revision, memo, or research</small></span>
              <em>{authConfig?.manualIntakeEnabled ? 'READY' : 'STAGED'}</em>
            </div>
            <div className="laos-notice-policy">
              <span>RECEIPT ACKNOWLEDGEMENT <strong>DRAFT FOR APPROVAL</strong></span>
              <span>COMPLETION NOTICE <strong>DRAFT FOR APPROVAL</strong></span>
            </div>
          </article>

          <article className="panel laos-intake-launch">
            <div className="panel-h">
              <span className="t">MATTER LAUNCH WORKSPACE</span>
              <span className="corner">INTAKE V1.1</span>
            </div>
            <div className="laos-intake-launch-body">
              <p>Open the complete workspace to choose an exact document type, enter matter details, define conflicts and deadlines, or request Cyrano transcription services.</p>
              <button className="btn solid" type="button" onClick={() => setView('intake')}>
                OPEN COMPLETE MATTER INTAKE
              </button>
            </div>
          </article>
        </div>
      )}

      {view === 'intake' && (
        <article className="panel laos-intake-workspace">
          <div className="panel-h">
            <span className="t">MANUAL MATTER LAUNCH · INTAKE V1.1</span>
            <span className="corner">SC CIVIL · APPEAL · CYRANO</span>
          </div>
          {!operatorSession ? (
            <div className="laos-intake-locked">
              <strong>OPERATOR SIGN-IN REQUIRED</strong>
              <p>Sign in above with jeff@sri-intel.com to unlock the private matter workspace.</p>
            </div>
          ) : !authConfig?.manualIntakeEnabled ? (
            <div className="laos-intake-locked">
              <strong>CANONICAL INTAKE CONNECTION NOT CONFIGURED</strong>
              <p>The Command Center will not create local legal state. Configure the Legal Agent OS API connection to enable submission.</p>
            </div>
          ) : (
            <LegalManualIntakeWorkspace operatorEmail={operatorSession.email} onCreated={refreshDashboard} />
          )}
        </article>
      )}

      {(view === 'overview' || view === 'review') && (
        <div className="laos-lower-grid">
          <article className="panel">
            <div className="panel-h">
              <span className="t">REVIEW + DELIVERY</span>
              <span className="corner">
                {awaitingReviewPackets.length
                  ? `${awaitingReviewPackets.length} ${awaitingReviewPackets.length === 1 ? 'PACKET' : 'PACKETS'}`
                  : qualityReviewMatters.length
                  ? `${qualityReviewMatters.length} IN PROGRESS`
                  : `${awaitingApproval} ${awaitingApproval === 1 ? 'PACKET' : 'PACKETS'}`}
              </span>
            </div>
            {awaitingReviewPackets.length ? (
              <div className="laos-review-packets">
                {awaitingReviewPackets.map(packet => (
                  <section className="laos-review-packet" key={packet.packetId}>
                    <div className="laos-review-packet-head">
                      <span>
                        <strong>{matters.find(matter => matter.matterId === packet.matterId)?.displayName ?? packet.matterId}</strong>
                        <small>{packet.matterId} · PACKET V{packet.matterVersion}</small>
                      </span>
                      <em>AWAITING YOUR DECISION</em>
                    </div>
                    <p>{packet.summary}</p>

                    <div className="laos-review-artifacts">
                      {packet.artifacts.map(artifact => (
                        <a
                          href={`https://drive.google.com/open?id=${encodeURIComponent(artifact.driveFileId)}`}
                          key={`${artifact.driveFileId}-${artifact.sha256}`}
                          rel="noreferrer"
                          target="_blank"
                        >
                          <strong>{artifact.title}</strong>
                          <small>{artifact.kind.replace(/_/g, ' ').toUpperCase()} · OPEN IN PRIVATE DRIVE</small>
                        </a>
                      ))}
                    </div>

                    <div className="laos-review-findings">
                      <div><strong>AUTHORITIES</strong><ul>{packet.authorities.length ? packet.authorities.map(item => <li key={item}>{item}</li>) : <li>None listed</li>}</ul></div>
                      <div><strong>CITATION FINDINGS</strong><ul>{packet.citationFindings.length ? packet.citationFindings.map(item => <li key={item}>{item}</li>) : <li>None listed</li>}</ul></div>
                      <div><strong>RISK FLAGS</strong><ul>{packet.riskFlags.length ? packet.riskFlags.map(item => <li key={item}>{item}</li>) : <li>None listed</li>}</ul></div>
                    </div>

                    {packet.proposedExternalAction && (
                      <div className="laos-delivery-gate">
                        <strong>PROPOSED FUTURE EXTERNAL ACTION · NOT AUTHORIZED</strong>
                        <p>{packet.proposedExternalAction}</p>
                      </div>
                    )}

                    <label className="laos-review-note">
                      DECISION NOTE · REQUIRED
                      <textarea
                        onChange={event => setReviewNotes(current => ({
                          ...current,
                          [packet.packetId]: event.target.value,
                        }))}
                        placeholder="Record your approval, revision instructions, or reason for rejection."
                        value={reviewNotes[packet.packetId] ?? ''}
                      />
                    </label>
                    <div className="laos-review-actions">
                      <button
                        className="btn solid"
                        disabled={reviewBusyId === packet.packetId || !(reviewNotes[packet.packetId]?.trim())}
                        onClick={() => handleReviewDecision(packet, 'approve')}
                        type="button"
                      >
                        APPROVE WORK PRODUCT
                      </button>
                      <button
                        className="btn"
                        disabled={reviewBusyId === packet.packetId || !(reviewNotes[packet.packetId]?.trim())}
                        onClick={() => handleReviewDecision(packet, 'request_revision')}
                        type="button"
                      >
                        REQUEST REVISION
                      </button>
                      <button
                        className="btn danger"
                        disabled={reviewBusyId === packet.packetId || !(reviewNotes[packet.packetId]?.trim())}
                        onClick={() => handleReviewDecision(packet, 'reject')}
                        type="button"
                      >
                        REJECT
                      </button>
                    </div>
                    <small className="laos-review-control-note">
                      Approving this packet does not authorize email, delivery, filing, calendar activity, or any other external action.
                    </small>
                  </section>
                ))}
              </div>
            ) : qualityReviewMatters.length ? (
              <div className="laos-review-empty" role="status" aria-live="polite">
                <span>QA</span>
                <div>
                  <strong>QUALITY REVIEW UNDERWAY</strong>
                  <p>
                    {qualityReviewMatters.map(matter => matter.displayName).join(', ')} — the
                    completed review {qualityReviewMatters.length === 1 ? 'packet' : 'packets'} will
                    appear here automatically when internal QA and packet assembly finish.
                  </p>
                </div>
              </div>
            ) : (
              <div className="laos-review-empty">
                <span>QA</span>
                <div>
                  <strong>NOTHING NEEDS YOUR DECISION</strong>
                  <p>Completed work appears here with the source record, draft, authorities, citation findings, risk flags, and exact proposed external action.</p>
                </div>
              </div>
            )}
          </article>

          <article className="panel">
              <div className="panel-h">
                <span className="t">CONNECTOR READINESS</span>
                <span className="corner">{readyConnectors} READY · {stagedConnectors} STAGED</span>
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
