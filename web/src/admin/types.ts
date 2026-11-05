import type { ReactNode } from "react";
import type { MasterApi, MasterType, Rec } from "../masterApi";
import type { Role } from "../ui/RoleGate/RoleGate";

export type Values = Record<string, string>;
export type Refs = Partial<Record<MasterType, Rec[]>>;

export type FieldDef = {
  key: string;
  label: string;
  kind: "text" | "int" | "select" | "bool";
  required?: boolean;
  /** Initial value of a new record. */
  default?: string;
  options?: { value: string; label: string }[];
  /** Options are the active records of another type (value = id, label = name). */
  optionsFrom?: MasterType;
  hint?: (values: Values) => string | undefined;
};

/** What the record panel hands to the per-type extras (contacts, coverage, approved fuels). */
export type ExtraCtx = {
  rec: Rec;
  refs: Refs;
  api: MasterApi;
  roles: Role[];
  onFail: (e: unknown) => void;
  /** Refetch the record and lists; unsaved drafts stay. */
  reload: () => void;
  /** Bumps when a conflict forces everything to reset to the server state. */
  epoch: number;
};

export type MasterConfig = {
  path: MasterType;
  title: string;
  singular: string;
  fields: FieldDef[];
  columns: { key: string; header: string; render: (row: Rec, refs: Refs) => ReactNode }[];
  /** Other types this page needs for selects and matrices. */
  refs: MasterType[];
  /** Rendered inside the record panel, under the form. */
  aside?: (ctx: ExtraCtx) => ReactNode;
  /** Rendered full width under the list and panel. */
  below?: (ctx: ExtraCtx) => ReactNode;
};
