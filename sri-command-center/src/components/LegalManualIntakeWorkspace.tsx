"use client";

import { FormEvent, useMemo, useState } from "react";
import outputCatalog from "../data/document-output-types.sc.v1.json";
import CompleteNewMatterQuestionnaire from "./CompleteNewMatterQuestionnaire";
import { submitLegalIntake } from "../api/client";

type SubmitState =
  | { kind: "idle" }
  | { kind: "working" }
  | { kind: "success"; message: string }
  | { kind: "error"; message: string };

type CatalogOutput = (typeof outputCatalog.outputs)[number];

type DeliverableDraft = {
  key: string;
  family: string;
  documentType: string;
  title: string;
  stage: "first_draft" | "revision" | "review_redline" | "research_only" | "final_for_signature" | "transcription";
  recipient: string;
  dueDate: string;
  pageOrWordLimit: string;
  sourceArtifactId: string;
  instructions: string;
};

function availableOutputs(requestType: string, practiceLane: string): CatalogOutput[] {
  return outputCatalog.outputs.filter(
    (output) => output.request_types.includes(requestType) && output.lanes.includes(practiceLane),
  );
}

function initialDeliverable(requestType: string, practiceLane: string): DeliverableDraft {
  const first = availableOutputs(requestType, practiceLane)[0];
  return {
    key: crypto.randomUUID(),
    family: first?.family ?? "research_advisory",
    documentType: first?.code ?? "RES-MEMO-FORMAL",
    title: "",
    stage: requestType === "revision" ? "revision" : requestType === "standalone_research" ? "research_only" : requestType === "transcription" ? "transcription" : "first_draft",
    recipient: "",
    dueDate: "",
    pageOrWordLimit: "",
    sourceArtifactId: "",
    instructions: "",
  };
}

export default function LegalManualIntakeWorkspace({
  operatorEmail,
  onCreated,
}: {
  operatorEmail: string;
  onCreated?: () => void;
}) {
  const [requestType, setRequestType] = useState("new_matter");
  const [practiceLane, setPracticeLane] = useState("civil");
  const [intakeDepth, setIntakeDepth] = useState<"complete" | "quick">("complete");
  const [questionnaireAnswers, setQuestionnaireAnswers] = useState<Record<string, unknown>>({
    matter_track: "Litigation (state)",
    controlling_jurisdiction: "South Carolina",
    no_external_deadline: false,
  });
  const [deliverables, setDeliverables] = useState<DeliverableDraft[]>(() => [initialDeliverable("new_matter", "civil")]);
  const [state, setState] = useState<SubmitState>({ kind: "idle" });

  const filteredOutputs = useMemo(
    () => availableOutputs(requestType, practiceLane),
    [requestType, practiceLane],
  );
  const availableFamilies = useMemo(
    () => outputCatalog.families.filter((family) => filteredOutputs.some((output) => output.family === family.code)),
    [filteredOutputs],
  );

  function changeRequestType(value: string) {
    setRequestType(value);
    if (value !== "new_matter") setIntakeDepth("quick");
    setDeliverables([initialDeliverable(value, practiceLane)]);
  }

  function changePracticeLane(value: string) {
    setPracticeLane(value);
    setQuestionnaireAnswers((current) => ({
      ...current,
      matter_track: value === "appeal" ? "Litigation (appellate)" : current.matter_track === "Litigation (appellate)" ? "Litigation (state)" : current.matter_track,
    }));
    setDeliverables([initialDeliverable(requestType, value)]);
  }

  function changeQuestionnaire(next: Record<string, unknown>) {
    const nextTrack = String(next.matter_track ?? "");
    const nextLane = nextTrack === "Litigation (appellate)" ? "appeal" : practiceLane === "appeal" ? "civil" : practiceLane;
    if (nextLane !== practiceLane) {
      setPracticeLane(nextLane);
      setDeliverables([initialDeliverable(requestType, nextLane)]);
    }
    setQuestionnaireAnswers(next);
  }

  function updateDeliverable(key: string, update: Partial<DeliverableDraft>) {
    setDeliverables((current) => current.map((item) => item.key === key ? { ...item, ...update } : item));
  }

  function selectFamily(key: string, family: string) {
    const first = filteredOutputs.find((output) => output.family === family);
    if (first) updateDeliverable(key, { family, documentType: first.code });
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState({ kind: "working" });
    const form = new FormData(event.currentTarget);
    const lines = (name: string) =>
      String(form.get(name) ?? "").split("\n").map((value) => value.trim()).filter(Boolean);
    const isTranscript = requestType === "transcription";
    const transcriptFormat = deliverables[0]?.documentType === "TRANSCRIPT-LITIGATION-FORMATTED"
      ? "litigation_formatted"
      : "unformatted";
    const structuredDeliverables = deliverables.map((deliverable) => ({
      document_type: deliverable.documentType,
      title: deliverable.title || null,
      stage: requestType === "revision" ? "revision" : requestType === "standalone_research" ? "research_only" : requestType === "transcription" ? "transcription" : deliverable.stage,
      recipient: deliverable.recipient || null,
      due_date: deliverable.dueDate || null,
      page_or_word_limit: deliverable.pageOrWordLimit || null,
      source_artifact_id: deliverable.sourceArtifactId || null,
      instructions: deliverable.instructions,
    }));
    const adverseParties = Array.isArray(questionnaireAnswers.adverse_parties)
      ? questionnaireAnswers.adverse_parties as Array<Record<string, unknown>>
      : [];
    const questionnaireConflictNames = adverseParties.map((party) => String(party.name ?? "").trim()).filter(Boolean);
    const questionnaireClients = Array.isArray(questionnaireAnswers.clients)
      ? questionnaireAnswers.clients as Array<Record<string, unknown>>
      : [];
    const questionnaireDeadline = String(questionnaireAnswers.hard_deadline ?? "").slice(0, 10);
    const payload = {
      schema_version: "1.1",
      channel: "manual",
      source_id: crypto.randomUUID(),
      request_type: requestType,
      subject: form.get("subject"),
      body: form.get("body"),
      attorney: {
        name: form.get("attorneyName"),
        email: form.get("attorneyEmail"),
        firm_name: form.get("firmName"),
        licensing_jurisdictions: [form.get("licenseJurisdiction")],
      },
      client_name: form.get("clientName") || questionnaireClients[0]?.legal_name || null,
      matter_id: form.get("matterId") || null,
      jurisdiction: form.get("jurisdiction"),
      forum_jurisdiction: form.get("forumJurisdiction") || null,
      court: form.get("court") || questionnaireAnswers.court_name || null,
      case_number: form.get("caseNumber") || questionnaireAnswers.case_number || null,
      practice_lane: practiceLane,
      conflict_names: [...new Set([...lines("conflictNames"), ...questionnaireConflictNames])],
      requested_deliverables: deliverables.map((deliverable) => outputCatalog.outputs.find((output) => output.code === deliverable.documentType)?.label ?? deliverable.documentType),
      deliverables: structuredDeliverables,
      deadline: form.get("deadline") || questionnaireDeadline || null,
      priority: form.get("priority"),
      confidentiality: form.get("confidentiality"),
      operator_notes: form.get("operatorNotes"),
      questionnaire_answers: requestType === "new_matter" && intakeDepth === "complete" ? questionnaireAnswers : {},
      transcription: isTranscript ? {
        format: transcriptFormat,
        audio_minutes: Number(form.get("audioMinutes")),
        turnaround: form.get("turnaround"),
        named_speakers: form.get("namedSpeakers") === "on",
        paragraph_timestamps: form.get("paragraphTimestamps") === "on",
        keyword_highlighting: form.get("keywordHighlighting") === "on",
        concept_highlighting: form.get("conceptHighlighting") === "on",
        concise_summary: form.get("conciseSummary") === "on",
        chronology: form.get("chronology") === "on",
        names_authorities_exhibit_index: form.get("index") === "on",
        poor_audio_review: form.get("poorAudioReview") === "on",
        official_or_certified_requested: false,
      } : null,
    };

    try {
      const result = await submitLegalIntake(payload);
      setState({ kind: "success", message: `${result.matter.matterId} was received and is awaiting intake validation.` });
      onCreated?.();
      event.currentTarget.reset();
      setRequestType("new_matter");
      setPracticeLane("civil");
      setIntakeDepth("complete");
      setQuestionnaireAnswers({
        matter_track: "Litigation (state)",
        controlling_jurisdiction: "South Carolina",
        no_external_deadline: false,
      });
      setDeliverables([initialDeliverable("new_matter", "civil")]);
    } catch (error) {
      setState({ kind: "error", message: error instanceof Error ? error.message : "The intake could not be saved." });
    }
  }

  return (
    <form className="intake-form" onSubmit={submit}>
      <div className="form-context">Signed in as <strong>{operatorEmail}</strong>. No message, filing, or customer delivery will be sent from this form.</div>
      <div className="form-grid">
        <label>Request type<select name="requestType" value={requestType} onChange={(event) => changeRequestType(event.target.value)}><option value="new_matter">New matter</option><option value="revision">Revision</option><option value="strategy_memo">Strategy memo</option><option value="standalone_research">Standalone research</option><option value="transcription">Transcription</option></select></label>
        <label>Existing matter ID {requestType === "revision" ? "(required)" : ""}<input name="matterId" required={requestType === "revision"} /></label>
        {requestType === "new_matter" ? <label>Intake depth<select value={intakeDepth} onChange={(event) => setIntakeDepth(event.target.value as "complete" | "quick")}><option value="complete">Complete new-matter questionnaire</option><option value="quick">Quick operator intake</option></select></label> : null}
        <label className="span-2">Assignment title<input name="subject" required maxLength={500} /></label>
        <label className="span-2">Matter or assignment details<textarea name="body" required rows={5} maxLength={100000} /></label>
        <label>Review attorney / recipient<input name="attorneyName" required /></label>
        <label>Attorney email<input name="attorneyEmail" type="email" required /></label>
        <label>Firm<input name="firmName" required /></label>
        <label>Attorney licensing jurisdiction<input name="licenseJurisdiction" defaultValue="SC" required /></label>
        <label>Client<input name="clientName" /></label>
        <label>Controlling jurisdiction<input name="jurisdiction" defaultValue="SC" required /></label>
        <label>Forum jurisdiction<input name="forumJurisdiction" defaultValue="South Carolina" /></label>
        <label>Court<input name="court" /></label>
        <label>Case number<input name="caseNumber" /></label>
        <label>Practice lane<select name="practiceLane" value={practiceLane} onChange={(event) => changePracticeLane(event.target.value)}><option value="civil">Civil</option><option value="appeal">Appeal</option></select></label>
        <label>Deadline<input name="deadline" type="date" /></label>
        <label>Priority<select name="priority" defaultValue="standard"><option value="standard">Standard</option><option value="priority">Priority</option><option value="urgent">Urgent</option></select></label>
        <label>Confidentiality<select name="confidentiality" defaultValue="privileged"><option value="privileged">Privileged</option><option value="restricted">Restricted</option><option value="standard">Standard</option></select></label>
        <label className="span-2">Conflict and adverse-party names (one per line)<textarea name="conflictNames" rows={4} /></label>
        <label className="span-2">Operator notes and workflow instructions<textarea name="operatorNotes" rows={4} /></label>
      </div>

      <fieldset className="deliverable-options">
        <legend>Requested documents and outputs</legend>
        <p className="form-context">Choose the exact output type. Add a separate entry when the assignment requires more than one document.</p>
        <div className="deliverable-list">
          {deliverables.map((deliverable, index) => {
            const outputsForFamily = filteredOutputs.filter((output) => output.family === deliverable.family);
            return (
              <section className="deliverable-card" key={deliverable.key}>
                <div className="deliverable-heading">
                  <strong>Deliverable {index + 1}</strong>
                  {deliverables.length > 1 ? <button className="secondary-button" type="button" onClick={() => setDeliverables((current) => current.filter((item) => item.key !== deliverable.key))}>Remove</button> : null}
                </div>
                <div className="form-grid">
                  <label>Document family<select aria-label={`Document family ${index + 1}`} value={deliverable.family} onChange={(event) => selectFamily(deliverable.key, event.target.value)}>{availableFamilies.map((family) => <option key={family.code} value={family.code}>{family.label}</option>)}</select></label>
                  <label>Exact document or output type<select aria-label={`Exact document or output type ${index + 1}`} value={deliverable.documentType} onChange={(event) => updateDeliverable(deliverable.key, { documentType: event.target.value })}>{outputsForFamily.map((output) => <option key={output.code} value={output.code}>{output.label}</option>)}</select></label>
                  <label>Document title (optional)<input value={deliverable.title} onChange={(event) => updateDeliverable(deliverable.key, { title: event.target.value })} /></label>
                  <label>Stage<select value={deliverable.stage} disabled={requestType === "revision" || requestType === "standalone_research" || requestType === "transcription"} onChange={(event) => updateDeliverable(deliverable.key, { stage: event.target.value as DeliverableDraft["stage"] })}><option value="first_draft">First draft</option><option value="revision">Revision of existing draft</option><option value="review_redline">Review and redline</option><option value="research_only">Research only</option><option value="final_for_signature">Final for signature</option><option value="transcription">Transcription</option></select></label>
                  <label>Filing court or recipient<input value={deliverable.recipient} onChange={(event) => updateDeliverable(deliverable.key, { recipient: event.target.value })} /></label>
                  <label>Deliverable due date<input type="date" value={deliverable.dueDate} onChange={(event) => updateDeliverable(deliverable.key, { dueDate: event.target.value })} /></label>
                  <label>Page or word limit<input value={deliverable.pageOrWordLimit} onChange={(event) => updateDeliverable(deliverable.key, { pageOrWordLimit: event.target.value })} /></label>
                  {requestType === "revision" ? <label>Source artifact or prior version ID<input value={deliverable.sourceArtifactId} onChange={(event) => updateDeliverable(deliverable.key, { sourceArtifactId: event.target.value })} /></label> : null}
                  <label className="span-2">Document-specific instructions<textarea rows={3} value={deliverable.instructions} onChange={(event) => updateDeliverable(deliverable.key, { instructions: event.target.value })} /></label>
                </div>
              </section>
            );
          })}
        </div>
        {requestType !== "transcription" ? <button className="secondary-button" type="button" onClick={() => setDeliverables((current) => [...current, initialDeliverable(requestType, practiceLane)])}>Add another deliverable</button> : null}
      </fieldset>

      {requestType === "new_matter" && intakeDepth === "complete" ? <CompleteNewMatterQuestionnaire answers={questionnaireAnswers} onChange={changeQuestionnaire} /> : null}

      {requestType === "transcription" ? (
        <fieldset className="transcription-options">
          <legend>Transcription options</legend>
          <div className="form-grid">
            <label>Audio minutes<input name="audioMinutes" type="number" min="1" step="0.1" required /></label>
            <label>Turnaround<select name="turnaround" defaultValue="standard"><option value="standard">Standard</option><option value="priority">Priority</option><option value="same_day">Same day</option></select></label>
          </div>
          <div className="check-grid">
            {[["namedSpeakers", "Named speakers"], ["paragraphTimestamps", "Paragraph timestamps"], ["keywordHighlighting", "Keyword highlighting"], ["conceptHighlighting", "Concept highlighting"], ["conciseSummary", "Concise summary"], ["chronology", "Chronology"], ["index", "Names / authorities / exhibit index"], ["poorAudioReview", "Enhanced poor-audio review"]].map(([name, label]) => <label className="check-label" key={name}><input name={name} type="checkbox" /> {label}</label>)}
          </div>
          <p className="transcript-notice">This service produces attorney work product, not an official or certified court transcript.</p>
        </fieldset>
      ) : null}

      <p className="form-context">SRI independently prepares the requested materials. The attorney receives the deliverables for review and does not receive direct access to the Legal Agent OS.</p>
      <div className="form-submit-row">
        <button disabled={state.kind === "working"} type="submit">{state.kind === "working" ? "Saving…" : "Create intake"}</button>
        {state.kind === "success" || state.kind === "error" ? <p className={`form-message ${state.kind}`} role="status">{state.message}</p> : null}
      </div>
    </form>
  );
}
