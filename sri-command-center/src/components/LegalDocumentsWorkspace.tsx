import { useEffect, useState } from 'react';
import {
  getLegalDocumentPreview,
  getLegalMatterDocuments,
  reviewLegalMatterDocument,
  uploadLegalMatterDocument,
} from '../api/client';
import type { LegalDocumentExtractionPreview, LegalMatterDocument } from '../types';

const CATEGORIES = [
  ['client_intake', 'Client intake'],
  ['attorney_strategy', 'Attorney strategy notes'],
  ['filed_pleading', 'Filed pleading'],
  ['court_order', 'Court order'],
  ['motion_or_brief', 'Motion or brief'],
  ['discovery', 'Discovery'],
  ['transcript', 'Transcript'],
  ['exhibit', 'Exhibit'],
  ['correspondence', 'Correspondence'],
  ['prior_draft', 'Prior draft'],
  ['other', 'Other'],
] as const;

export default function LegalDocumentsWorkspace({ matterId }: { matterId: string }) {
  const [documents, setDocuments] = useState<LegalMatterDocument[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [category, setCategory] = useState('other');
  const [recordStatus, setRecordStatus] = useState('received');
  const [confidentiality, setConfidentiality] = useState('privileged');
  const [preview, setPreview] = useState<LegalDocumentExtractionPreview | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  const refresh = async () => setDocuments(await getLegalMatterDocuments(matterId));

  useEffect(() => {
    setPreview(null);
    setMessage('');
    refresh().catch(error => setMessage(error instanceof Error ? error.message : 'Documents could not be loaded.'));
  }, [matterId]);

  const upload = async () => {
    if (!selectedFile) return;
    setBusy(true);
    setMessage('');
    try {
      const document = await uploadLegalMatterDocument(matterId, selectedFile, {
        category,
        recordStatus,
        confidentiality,
      });
      await refresh();
      setSelectedFile(null);
      setMessage(
        document.ingestionStatus === 'needs_ocr'
          ? `${document.name} was preserved but requires OCR before it can enter context.`
          : `${document.name} was preserved and extracted for your review.`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Document upload failed.');
    } finally {
      setBusy(false);
    }
  };

  const inspect = async (document: LegalMatterDocument) => {
    setBusy(true);
    setMessage('');
    try {
      setPreview(await getLegalDocumentPreview(matterId, document.documentId));
      setNote(document.reviewNote ?? '');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Extraction preview could not be loaded.');
    } finally {
      setBusy(false);
    }
  };

  const decide = async (action: 'accept' | 'exclude' | 'supersede') => {
    if (!preview) return;
    setBusy(true);
    setMessage('');
    try {
      const updated = await reviewLegalMatterDocument(
        matterId,
        preview.document.documentId,
        action,
        preview.document.version,
        note.trim(),
      );
      await refresh();
      setPreview(current => current ? { ...current, document: updated } : null);
      setMessage(
        action === 'accept'
          ? `${updated.name} is now available to this matter's research and drafting context.`
          : `${updated.name} was ${action === 'exclude' ? 'excluded from' : 'marked superseded in'} matter context.`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Document decision failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="legal-documents-workspace">
      <article className="panel legal-document-upload">
        <div className="panel-h"><span className="t">ADD CASE DOCUMENTS</span><span className="corner">PRIVATE DRIVE · 25 MB MAX</span></div>
        <div className="document-upload-grid">
          <label className="file-drop">Choose PDF, Word, email, or text file<input type="file" accept=".pdf,.docx,.txt,.md,.json,.eml,.csv" onChange={event => setSelectedFile(event.target.files?.[0] ?? null)} /></label>
          <label>Document type<select value={category} onChange={event => setCategory(event.target.value)}>{CATEGORIES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
          <label>Record status<select value={recordStatus} onChange={event => setRecordStatus(event.target.value)}><option value="received">Received</option><option value="draft">Draft</option><option value="proposed">Proposed</option><option value="filed">Filed</option><option value="operative">Operative</option><option value="superseded">Superseded</option></select></label>
          <label>Confidentiality<select value={confidentiality} onChange={event => setConfidentiality(event.target.value)}><option value="privileged">Privileged</option><option value="restricted">Restricted</option><option value="standard">Standard</option></select></label>
          <button className="btn solid" type="button" disabled={!selectedFile || busy} onClick={upload}>{busy ? 'PROCESSING…' : 'UPLOAD + EXTRACT'}</button>
        </div>
        <p className="document-privacy-note">Originals remain unchanged. Extracted text is stored as a checksum-linked Drive sidecar and is excluded from AI context until accepted below.</p>
      </article>

      <article className="panel legal-document-list">
        <div className="panel-h"><span className="t">DOCUMENTS & SOURCES</span><span className="corner">{documents.length} FILES</span></div>
        {documents.length === 0 ? <p className="legal-doc-empty">No source documents have been added to this matter.</p> : documents.map(document => (
          <button className="legal-document-row" type="button" key={document.documentId} onClick={() => inspect(document)}>
            <span><strong>{document.name}</strong><small>{document.category.replace(/_/g, ' ')} · {document.recordStatus} · {Math.max(1, Math.round(document.sizeBytes / 1024))} KB</small></span>
            <em className={`document-status ${document.ingestionStatus}`}>{document.ingestionStatus.replace(/_/g, ' ')}</em>
          </button>
        ))}
      </article>

      {preview ? (
        <article className="panel legal-document-preview">
          <div className="panel-h"><span className="t">EXTRACTION REVIEW</span><a href={`https://drive.google.com/open?id=${encodeURIComponent(preview.document.driveFileId)}`} target="_blank" rel="noreferrer">OPEN ORIGINAL</a></div>
          <div className="document-provenance">{preview.provenanceNotice}</div>
          {preview.document.warnings.map(warning => <p className="document-warning" key={warning}>{warning}</p>)}
          <pre>{preview.textExcerpt || 'No readable text is available. OCR or an unlocked source copy is required.'}</pre>
          <label>Review note<textarea rows={3} value={note} onChange={event => setNote(event.target.value)} /></label>
          <div className="document-review-actions">
            <button className="btn solid" type="button" disabled={busy || preview.document.ingestionStatus !== 'ready_for_review'} onClick={() => decide('accept')}>ACCEPT INTO CONTEXT</button>
            <button className="secondary-button" type="button" disabled={busy} onClick={() => decide('exclude')}>EXCLUDE</button>
            <button className="secondary-button" type="button" disabled={busy} onClick={() => decide('supersede')}>MARK SUPERSEDED</button>
          </div>
        </article>
      ) : null}
      {message ? <p className="form-message" role="status">{message}</p> : null}
    </div>
  );
}
