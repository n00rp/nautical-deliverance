import { useEffect, useState } from "react";
import type { Body, Rec } from "../masterApi";
import { Button } from "../ui/Button/Button";
import { Checkbox } from "../ui/Checkbox/Checkbox";
import { FormSummary } from "../ui/FormSummary/FormSummary";
import { LockedNote } from "../ui/LockedNote/LockedNote";
import { NumberField } from "../ui/NumberField/NumberField";
import { RoleGate, type Role } from "../ui/RoleGate/RoleGate";
import { Select } from "../ui/Select/Select";
import { TextField } from "../ui/TextField/TextField";
import css from "./Admin.module.css";
import { useSave } from "./useSave";
import type { FieldDef, Refs, Values } from "./types";

export type EditFormProps = {
  /** Accessible name of the form. */
  name: string;
  fields: FieldDef[];
  initial: Values;
  refs: Refs;
  roles: Role[];
  submitLabel: string;
  onSubmit: (body: Body) => Promise<void>;
  /** Anything that is not a field error or a 403. */
  onFail: (e: unknown) => void;
  onCancel?: (() => void) | undefined;
  /** Fields side by side (for forms in the full-width area). */
  wide?: boolean;
};

export const initialValues = (fields: FieldDef[], rec?: Rec): Values =>
  Object.fromEntries(
    fields.map((f) => [f.key, rec ? String(rec[f.key] ?? "") : (f.default ?? "")]),
  );

function toBody(fields: FieldDef[], values: Values): Body {
  return Object.fromEntries(
    fields.map((f): [string, Body[string]] => {
      const v = (values[f.key] ?? "").trim();
      if (f.kind === "bool") return [f.key, v === "true"];
      if (f.kind === "int") return [f.key, v === "" ? null : Number(v)];
      return [f.key, v === "" && !f.required ? null : v];
    }),
  );
}

export function EditForm({
  name,
  fields,
  initial,
  refs,
  roles,
  submitLabel,
  onSubmit,
  onFail,
  onCancel,
  wide,
}: EditFormProps) {
  const [values, setValues] = useState(initial);
  const { form, issues, clear, forbidden, setForbidden, busy, submit } = useSave(onFail);
  const disabled = !roles.includes("admin");
  // A different role or a reloaded record may allow what was forbidden before.
  const context = `${roles.join()}|${JSON.stringify(initial)}`;
  useEffect(() => {
    setForbidden(false);
  }, [context, setForbidden]);
  const id = (key: string) => `${name.toLowerCase()}-${key}`;

  const set = (key: string, value: string) => {
    setValues((v) => ({ ...v, [key]: value }));
    clear((field) => field === key);
  };

  const control = (f: FieldDef) => {
    const common = {
      id: id(f.key),
      label: f.label,
      error: issues.find((i) => i.field === f.key)?.message,
      disabled,
      value: values[f.key] ?? "",
      onChange: (v: string) => {
        set(f.key, v);
      },
    };
    if (f.kind === "bool") {
      return (
        <Checkbox
          key={f.key}
          id={common.id}
          label={f.label}
          disabled={disabled}
          checked={common.value === "true"}
          onChange={(on) => {
            set(f.key, String(on));
          }}
        />
      );
    }
    if (f.kind === "int") {
      return <NumberField key={f.key} {...common} required={f.required} decimals={0} />;
    }
    if (f.kind === "select") {
      const options = f.optionsFrom
        ? (refs[f.optionsFrom] ?? []).map((r) => ({ value: r.id, label: String(r.name) }))
        : (f.options ?? []);
      return <Select key={f.key} {...common} required={f.required} options={options} />;
    }
    return <TextField key={f.key} {...common} required={f.required} hint={f.hint?.(values)} />;
  };

  return (
    <form
      ref={form}
      aria-label={name}
      noValidate
      className={wide ? css.grid : css.form}
      onSubmit={(e) => void submit(() => onSubmit(toBody(fields, values)))(e)}
    >
      <div className={css.span}>
        <FormSummary errors={issues.map((i) => ({ fieldId: id(i.field), message: i.message }))} />
      </div>
      {fields.map(control)}
      <RoleGate allow={["admin"]} roles={roles} fallback={<LockedNote what="edit controls" />}>
        {forbidden ? (
          <LockedNote what="saving changes" />
        ) : (
          <div className={`${css.actions} ${css.span}`}>
            <Button type="submit" variant="primary" loading={busy}>
              {submitLabel}
            </Button>
            {onCancel && (
              <Button variant="ghost" onClick={onCancel}>
                Cancel
              </Button>
            )}
          </div>
        )}
      </RoleGate>
    </form>
  );
}
