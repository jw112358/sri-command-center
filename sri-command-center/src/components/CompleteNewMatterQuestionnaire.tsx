"use client";

import { useMemo, useState } from "react";
import intakeSchema from "../data/legal-matter-intake.v1.1.json";


type Condition = {
  field: string;
  op: "eq" | "ne" | "in" | "not_in" | "contains" | "is_true" | "is_false" | "any_of";
  value?: unknown;
};

type FieldSchema = {
  id: string;
  label: string;
  type: string;
  required?: boolean;
  required_if?: Condition;
  show_if?: Condition;
  help?: string;
  options?: string[];
  repeats?: boolean;
  internal_only?: boolean;
  sensitive?: boolean;
  subfields?: FieldSchema[];
};

type SectionSchema = {
  id: string;
  title: string;
  purpose?: string;
  show_if?: Condition;
  internal_only?: boolean;
  fields: FieldSchema[];
};

type Answers = Record<string, unknown>;


function conditionMatches(condition: Condition | undefined, answers: Answers): boolean {
  if (!condition) return true;
  const actual = answers[condition.field];
  const expected = condition.value;
  switch (condition.op) {
    case "eq": return actual === expected;
    case "ne": return actual !== expected;
    case "in": return Array.isArray(expected) && expected.includes(actual);
    case "not_in": return Array.isArray(expected) && !expected.includes(actual);
    case "contains": return Array.isArray(actual) ? actual.includes(expected) : String(actual ?? "").includes(String(expected ?? ""));
    case "is_true": return actual === true;
    case "is_false": return actual !== true;
    case "any_of": return Array.isArray(expected) && expected.some((item) => item === actual);
  }
}


function scalarValue(value: unknown): string | number {
  return typeof value === "number" ? value : typeof value === "string" ? value : "";
}


function FieldControl({
  field,
  answers,
  onChange,
}: {
  field: FieldSchema;
  answers: Answers;
  onChange: (id: string, value: unknown) => void;
}) {
  if (field.internal_only || !conditionMatches(field.show_if, answers)) return null;
  const value = answers[field.id];
  const required = Boolean(field.required || (field.required_if && conditionMatches(field.required_if, answers)));

  if (field.type === "group") {
    const rows = Array.isArray(value) ? value as Answers[] : [];
    const visibleRows = rows.length ? rows : [{}];
    const updateRow = (index: number, id: string, nextValue: unknown) => {
      const nextRows = visibleRows.map((row, rowIndex) => rowIndex === index ? { ...row, [id]: nextValue } : row);
      onChange(field.id, nextRows);
    };
    return (
      <fieldset className="questionnaire-group">
        <legend>{field.label}{required ? " *" : ""}</legend>
        {field.help ? <p className="field-help">{field.help}</p> : null}
        {visibleRows.map((row, index) => (
          <div className="questionnaire-group-row" key={`${field.id}-${index}`}>
            <div className="questionnaire-group-heading">
              <strong>{field.label} {index + 1}</strong>
              {visibleRows.length > 1 ? <button className="secondary-button" type="button" onClick={() => onChange(field.id, visibleRows.filter((_, rowIndex) => rowIndex !== index))}>Remove</button> : null}
            </div>
            <div className="form-grid">
              {(field.subfields ?? []).map((subfield) => <FieldControl field={subfield} answers={row} onChange={(id, nextValue) => updateRow(index, id, nextValue)} key={`${field.id}-${index}-${subfield.id}`} />)}
            </div>
          </div>
        ))}
        {field.repeats ? <button className="secondary-button" type="button" onClick={() => onChange(field.id, [...visibleRows, {}])}>Add another</button> : null}
      </fieldset>
    );
  }

  if (field.type === "boolean") {
    return (
      <label className="check-label questionnaire-check">
        <input checked={value === true} required={required} type="checkbox" onChange={(event) => onChange(field.id, event.target.checked)} />
        <span>{field.label}{required ? " *" : ""}{field.help ? <small className="field-help">{field.help}</small> : null}</span>
      </label>
    );
  }

  if (field.type === "select" || field.type === "multiselect") {
    const multiple = field.type === "multiselect";
    return (
      <label>{field.label}{required ? " *" : ""}
        <select multiple={multiple} required={required} value={multiple ? (Array.isArray(value) ? value as string[] : []) : String(value ?? "")} onChange={(event) => onChange(field.id, multiple ? Array.from(event.currentTarget.selectedOptions, (option) => option.value) : event.currentTarget.value)}>
          {!multiple ? <option value="">Select…</option> : null}
          {(field.options ?? []).map((option) => <option value={option} key={option}>{option}</option>)}
        </select>
        {field.help ? <small className="field-help">{field.help}</small> : null}
      </label>
    );
  }

  if (field.type === "textarea") {
    return (
      <label className="span-2">{field.label}{required ? " *" : ""}
        <textarea required={required} rows={4} value={String(value ?? "")} onChange={(event) => onChange(field.id, event.target.value)} />
        {field.help ? <small className="field-help">{field.help}</small> : null}
      </label>
    );
  }

  const inputType = {
    date: "date",
    datetime: "datetime-local",
    email: "email",
    phone: "tel",
    number: "number",
    currency: "number",
  }[field.type] ?? "text";
  return (
    <label>{field.label}{required ? " *" : ""}
      <input required={required} step={field.type === "currency" ? "0.01" : undefined} type={inputType} value={scalarValue(value)} onChange={(event) => onChange(field.id, field.type === "number" || field.type === "currency" ? (event.target.value === "" ? "" : Number(event.target.value)) : event.target.value)} />
      {field.help ? <small className="field-help">{field.help}</small> : null}
      {field.sensitive ? <small className="sensitive-help">Sensitive: provide only when necessary for the selected deliverable.</small> : null}
    </label>
  );
}


const EXCLUDED_SECTIONS = new Set(["s01_submission", "s05_services", "s18_internal"]);


export default function CompleteNewMatterQuestionnaire({
  answers,
  onChange,
}: {
  answers: Answers;
  onChange: (answers: Answers) => void;
}) {
  const [step, setStep] = useState(0);
  const sections = useMemo(
    () => (intakeSchema.sections as SectionSchema[]).filter((section) => !EXCLUDED_SECTIONS.has(section.id) && !section.internal_only && conditionMatches(section.show_if, answers)),
    [answers],
  );
  const safeStep = Math.min(step, Math.max(sections.length - 1, 0));
  const current = sections[safeStep];
  if (!current) return null;

  return (
    <fieldset className="complete-questionnaire">
      <legend>Complete new-matter questionnaire</legend>
      <div className="questionnaire-progress">
        <span>Section {safeStep + 1} of {sections.length}</span>
        <progress max={sections.length} value={safeStep + 1} />
      </div>
      <div className="questionnaire-section">
        <p className="eyebrow">Detailed intake</p>
        <h3>{current.title}</h3>
        {current.purpose ? <p className="form-context">{current.purpose}</p> : null}
        <div className="form-grid">
          {current.fields.map((field) => <FieldControl field={field} answers={answers} onChange={(id, value) => onChange({ ...answers, [id]: value })} key={field.id} />)}
        </div>
      </div>
      <div className="questionnaire-navigation">
        <button className="secondary-button" disabled={safeStep === 0} type="button" onClick={() => setStep(Math.max(0, safeStep - 1))}>Previous section</button>
        <button className="secondary-button" disabled={safeStep === sections.length - 1} type="button" onClick={() => setStep(Math.min(sections.length - 1, safeStep + 1))}>Next section</button>
      </div>
      <p className="field-help">Complete-questionnaire answers are archived to the private Google Drive matter folder. They are not stored as unrestricted matter text in MongoDB.</p>
    </fieldset>
  );
}
