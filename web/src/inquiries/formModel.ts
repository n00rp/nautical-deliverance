// Form values of the inquiry page and their conversion to and from the API shapes.
import type { FieldIssue } from "../api";
import type { Inquiry, InquiryBody } from "../inquiryApi";
import type { Rec } from "../masterApi";

export type Unit = "mt" | "m3";

export type LineValues = {
  /** Stable React key; removing a line must not shift the others' field state. */
  key: number;
  product_id: string;
  quantity: string;
  unit: Unit;
  density: string;
  spec_notes: string;
  iso_spec_version_id: string;
};

const SCALARS = [
  "vessel_id",
  "legal_entity_id",
  "voyage",
  "operator_name",
  "buyer_id",
  "port_id",
  "eta",
  "etd",
  "agent_name",
  "agent_email",
  "bunkering_reason_id",
  "internal_comments",
] as const;
export type Scalar = (typeof SCALARS)[number];
export type Values = Record<Scalar, string> & { lines: LineValues[] };

export const MAX_LINES = 10;

let counter = 0;
export const newLine = (): LineValues => ({
  key: ++counter,
  product_id: "",
  quantity: "",
  unit: "mt",
  density: "",
  spec_notes: "",
  iso_spec_version_id: "",
});

const instant = (s: string | null) => (s ? new Date(s).toISOString() : "");

export function initialValues(rec: Inquiry | null): Values {
  if (!rec) {
    return {
      ...(Object.fromEntries(SCALARS.map((k) => [k, ""])) as Record<Scalar, string>),
      lines: [newLine()],
    };
  }
  return {
    vessel_id: rec.vessel_id,
    legal_entity_id: rec.legal_entity_id,
    voyage: rec.voyage ?? "",
    operator_name: rec.operator_name ?? "",
    buyer_id: rec.buyer_id ?? "",
    port_id: rec.port_id,
    eta: instant(rec.eta),
    etd: instant(rec.etd),
    agent_name: rec.agent_name ?? "",
    agent_email: rec.agent_email ?? "",
    bunkering_reason_id: rec.bunkering_reason_id,
    internal_comments: rec.internal_comments ?? "",
    lines: rec.lines.map((l) => ({
      key: ++counter,
      product_id: l.product_id,
      quantity: l.quantity,
      unit: l.unit === "m3" ? "m3" : "mt",
      density: l.density ?? "",
      spec_notes: l.spec_notes ?? "",
      iso_spec_version_id: l.iso_spec_version_id,
    })),
  };
}

const orNull = (s: string) => (s.trim() === "" ? null : s.trim());

/** Density only exists for m3 lines: an mt line never sends one (Review Focus 3). */
const toLine = (l: LineValues) => ({
  product_id: l.product_id,
  quantity: l.quantity,
  unit: l.unit,
  density: l.unit === "m3" ? orNull(l.density) : null,
  spec_notes: orNull(l.spec_notes),
  iso_spec_version_id: l.iso_spec_version_id,
});

/**
 * Legal entity and buyer left empty are omitted, so the engine fills its defaults. The operator
 * name is prefilled from the vessel in the form, so an empty one means the user cleared it: null.
 */
export function createBody(v: Values): InquiryBody {
  const body: InquiryBody = {
    vessel_id: v.vessel_id,
    port_id: v.port_id,
    eta: v.eta,
    etd: v.etd,
    bunkering_reason_id: v.bunkering_reason_id,
    voyage: orNull(v.voyage),
    operator_name: orNull(v.operator_name),
    agent_name: orNull(v.agent_name),
    agent_email: orNull(v.agent_email),
    internal_comments: orNull(v.internal_comments),
    lines: v.lines.map(toLine),
  };
  for (const k of ["legal_entity_id", "buyer_id"] as const) {
    if (v[k]) body[k] = v[k];
  }
  return body;
}

const linesOf = (v: Values) => JSON.stringify(v.lines.map(toLine));

/** Only the fields the user changed since the form was loaded; lines go as a whole set. */
export function patchBody(v: Values, base: Values): Partial<InquiryBody> {
  const body: Record<string, unknown> = {};
  for (const k of SCALARS) {
    if (v[k] !== base[k]) body[k] = orNull(v[k]);
  }
  if (linesOf(v) !== linesOf(base)) body.lines = v.lines.map(toLine);
  return body;
}

const text = (x: unknown) => (typeof x === "string" ? x : "");

/**
 * Review Focus 4: a new vessel brings its legal entity and default operator name, but only into
 * fields that are empty or still hold the previous vessel's defaults.
 */
export function pickVessel(v: Values, vessels: Rec[], id: string): Values {
  const prev = vessels.find((x) => x.id === v.vessel_id);
  const next = vessels.find((x) => x.id === id);
  const refill = (current: string, before: unknown, after: unknown) =>
    current === "" || current === text(before) ? text(after) : current;
  return {
    ...v,
    vessel_id: id,
    legal_entity_id: refill(v.legal_entity_id, prev?.legal_entity_id, next?.legal_entity_id),
    operator_name: refill(
      v.operator_name,
      prev?.default_operator_name,
      next?.default_operator_name,
    ),
  };
}

/** Element id of a field or of `lines[i].name`, so the error summary can link to it. */
export function fieldId(field: string): string {
  const m = /^lines\[(\d+)\]\.(\w+)$/.exec(field);
  return m ? `line-${m[1] ?? ""}-${m[2] ?? ""}` : `inq-${field}`;
}

export const issueFor = (issues: FieldIssue[], field: string) =>
  issues.find((i) => i.field === field)?.message;
