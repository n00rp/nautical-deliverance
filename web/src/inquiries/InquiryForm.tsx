import { useState } from "react";
import { useSave } from "../admin/useSave";
import type { DirectoryUser, Inquiry, InquiryBody } from "../inquiryApi";
import type { Rec } from "../masterApi";
import { Button } from "../ui/Button/Button";
import { DateTimeField } from "../ui/DateTimeField/DateTimeField";
import { FormSummary } from "../ui/FormSummary/FormSummary";
import { LockedNote } from "../ui/LockedNote/LockedNote";
import { Panel } from "../ui/Panel/Panel";
import type { Role } from "../ui/RoleGate/RoleGate";
import { Select } from "../ui/Select/Select";
import { TextField } from "../ui/TextField/TextField";
import admin from "../admin/Admin.module.css";
import css from "./Inquiry.module.css";
import {
  createBody,
  fieldId,
  initialValues,
  issueFor,
  patchBody,
  pickVessel,
  type Scalar,
  type Unit,
} from "./formModel";
import { LinesEditor, type Opt } from "./LinesEditor";

export type Refs = {
  vessels: Rec[];
  ports: Rec[];
  legalEntities: Rec[];
  products: Rec[];
  isos: Rec[];
  reasons: Rec[];
  /** Everyone in the directory, for names of users who no longer fit a picker. */
  users: DirectoryUser[];
  operators: DirectoryUser[];
  buyers: DirectoryUser[];
};

export type InquiryFormProps = {
  /** null: a new inquiry. */
  rec: Inquiry | null;
  refs: Refs;
  roles: Role[];
  onCreate: (body: InquiryBody) => Promise<void>;
  onPatch: (body: Partial<InquiryBody>) => Promise<void>;
  /** Anything that is not a field error or a 403. */
  onFail: (e: unknown) => void;
};

const names = (list: Rec[]): Opt[] => list.map((r) => ({ value: r.id, label: String(r.name) }));
const people = (list: DirectoryUser[]): Opt[] => list.map((u) => ({ value: u.id, label: u.name }));
/** A record that has since become inactive (or lost its role) still shows by name. */
const withCurrent = (opts: Opt[], id?: string | null, label?: string | null): Opt[] =>
  id && label && !opts.some((o) => o.value === id) ? [...opts, { value: id, label }] : opts;

const SENT_TO_SUPPLIERS = "Sent to suppliers in the RFQ";
const CREATE: Role[] = ["admin", "bunker_buyer", "operator"];
const EDIT: Role[] = ["admin", "bunker_buyer"];
const allowed = (roles: Role[], allow: Role[]) => roles.some((r) => allow.includes(r));

export function InquiryForm({ rec, refs, roles, onCreate, onPatch, onFail }: InquiryFormProps) {
  const [initial] = useState(() => initialValues(rec));
  const [values, setValues] = useState(initial);
  const { form, issues, clear, forbidden, busy, submit } = useSave(onFail);

  const canWrite = allowed(roles, rec ? EDIT : CREATE);
  const readOnly = !canWrite || rec?.status === "cancelled";
  const locked = rec !== null && rec.status !== "draft";
  const scopeOff = readOnly || locked;

  const set = (key: Scalar, value: string) => {
    setValues((v) => ({ ...v, [key]: value }));
    clear((field) => field === key);
  };
  const err = (key: Scalar) => issueFor(issues, key);
  const save = submit(() =>
    rec ? onPatch(patchBody(values, initial)) : onCreate(createBody(values)),
  );

  const vessel = refs.vessels.find((v) => v.id === values.vessel_id);
  const port = refs.ports.find((p) => p.id === values.port_id);
  const timeZone = port ? String(port.time_zone) : rec?.port_time_zone;
  const sel = (key: Scalar, label: string, options: Opt[], required = false, off = scopeOff) => (
    <Select
      id={fieldId(key)}
      label={label}
      required={required}
      value={values[key]}
      options={options}
      disabled={off}
      error={err(key)}
      onChange={(v) => {
        set(key, v);
      }}
    />
  );
  const text = (key: Scalar, label: string, off = readOnly, hint?: string) => (
    <TextField
      id={fieldId(key)}
      label={label}
      hint={hint}
      value={values[key]}
      disabled={off}
      error={err(key)}
      onChange={(v) => {
        set(key, v);
      }}
    />
  );
  const when = (key: "eta" | "etd", label: string) => (
    <DateTimeField
      id={fieldId(key)}
      label={label}
      required
      valueUtc={values[key]}
      timeZone={timeZone}
      disabled={readOnly}
      error={err(key)}
      onChange={(v) => {
        set(key, v);
      }}
    />
  );

  const warnings: Record<number, string[]> = {};
  for (const w of rec?.warnings ?? []) {
    const i = Number(/^lines\[(\d+)\]\./.exec(w.field)?.[1]);
    // A warning describes the saved line; it only applies while that line still holds the product.
    // After a vessel change the saved warnings are about the old vessel, so they are hidden.
    if (
      rec?.vessel_id === values.vessel_id &&
      rec.lines[i]?.product_id === values.lines[i]?.product_id
    ) {
      (warnings[i] ??= []).push(w.message);
    }
  }
  const defaultUnits = Object.fromEntries(
    refs.products.map((p) => [p.id, p.default_unit === "m3" ? "m3" : "mt"]),
  ) as Record<string, Unit>;
  const lines = rec?.lines ?? [];
  const products = lines.reduce(
    (o, l) => withCurrent(o, l.product_id, l.product_name),
    names(refs.products),
  );
  const isos = lines.reduce(
    (o, l) => withCurrent(o, l.iso_spec_version_id, l.iso_spec_version_name),
    names(refs.isos),
  );

  return (
    <form
      ref={form}
      aria-label="Inquiry"
      noValidate
      className={css.main}
      onSubmit={(e) => void save(e)}
    >
      <FormSummary
        errors={issues.map((i) => ({ fieldId: fieldId(i.field), message: i.message }))}
      />
      {!canWrite ? (
        <LockedNote what="edit controls" />
      ) : (
        locked && <LockedNote message="Locked after Draft — duplicate to change scope" />
      )}
      <Panel title="Vessel & voyage">
        <div className={css.stack}>
          <div className={admin.grid}>
            <Select
              id={fieldId("vessel_id")}
              label="Vessel"
              required
              value={values.vessel_id}
              options={withCurrent(names(refs.vessels), rec?.vessel_id, rec?.vessel_name)}
              disabled={scopeOff}
              error={err("vessel_id")}
              onChange={(id) => {
                setValues((v) => pickVessel(v, refs.vessels, id));
                clear((field) => field === "vessel_id");
              }}
            />
            {sel(
              "legal_entity_id",
              "Legal entity",
              withCurrent(names(refs.legalEntities), rec?.legal_entity_id, rec?.legal_entity_name),
            )}
            {text("voyage", "Voyage", scopeOff)}
            {sel(
              "operator_id",
              "Operator",
              withCurrent(people(refs.operators), rec?.operator_id, rec?.operator_name),
            )}
            {sel(
              "buyer_id",
              "Buyer",
              withCurrent(people(refs.buyers), rec?.buyer_id, rec?.buyer_name),
              false,
              readOnly,
            )}
          </div>
          {vessel && (
            <p className={css.info}>
              {`IMO ${String(vessel.imo)} · ${String(vessel.vessel_type)} · ${String(vessel.dwt)} DWT`}
            </p>
          )}
          {rec && <p className={css.info}>{`Requested by ${rec.requester_name}`}</p>}
        </div>
      </Panel>
      <Panel title="Port & timing">
        <div className={admin.grid}>
          {sel(
            "port_id",
            "Port",
            withCurrent(names(refs.ports), rec?.port_id, rec?.port_name),
            true,
          )}
          {when("eta", "ETA")}
          {when("etd", "ETD")}
          {text("agent_name", "Agent name", readOnly, SENT_TO_SUPPLIERS)}
          {text("agent_email", "Agent e-mail", readOnly)}
          {sel(
            "bunkering_reason_id",
            "Bunkering reason",
            withCurrent(names(refs.reasons), rec?.bunkering_reason_id, rec?.bunkering_reason_name),
            true,
          )}
        </div>
      </Panel>
      <Panel title="Products">
        <LinesEditor
          lines={values.lines}
          products={products}
          isos={isos}
          defaultUnits={defaultUnits}
          issues={issues}
          warnings={warnings}
          disabled={scopeOff}
          onChange={(lines) => {
            setValues((v) => ({ ...v, lines }));
            clear((field) => field.startsWith("lines"));
          }}
        />
      </Panel>
      <Panel title="Internal — never sent to suppliers">
        {text("internal_comments", "Internal comments")}
      </Panel>
      {!readOnly &&
        (forbidden ? (
          <LockedNote what="saving changes" />
        ) : (
          <div className={admin.actions}>
            <Button type="submit" variant="primary" loading={busy}>
              {rec ? "Save" : "Create inquiry"}
            </Button>
          </div>
        ))}
    </form>
  );
}
