import { useState } from "react";
import { Field } from "../Field/Field";
import styles from "../Field/Field.module.css";
import own from "./NumberField.module.css";
import { normalizeDecimal } from "./normalize";

export type NumberFieldProps = {
  id: string;
  label: string;
  /** Normalized decimal string `-?\d+(\.\d+)?` or "". Never a JS number (D-074). */
  value: string;
  onChange: (value: string) => void;
  decimals: number;
  unit?: string;
  error?: string;
  hint?: string;
  required?: boolean;
  disabled?: boolean;
};

export function NumberField({
  id,
  label,
  value,
  onChange,
  decimals,
  unit,
  disabled,
  error,
  ...field
}: NumberFieldProps) {
  // `draft` is what the user typed; null means "show the committed value".
  const [draft, setDraft] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | undefined>();

  const edit = (raw: string) => {
    setDraft(raw);
    const r = normalizeDecimal(raw, decimals);
    if ("value" in r) {
      setLocalError(undefined);
      onChange(r.value);
    } else {
      // Value stays unchanged; a trailing separator is merely unfinished, flagged on blur.
      setLocalError(/[.,]$/.test(raw) ? undefined : r.error);
    }
  };

  const blur = () => {
    if (draft === null) return;
    const r = normalizeDecimal(draft, decimals);
    if ("value" in r) setDraft(null);
    else setLocalError(r.error);
  };

  const unitId = unit ? `${id}-unit` : undefined;
  return (
    <Field id={id} label={label} error={error ?? localError} describedBy={unitId} {...field}>
      {(a11y) => (
        <span className={own.row}>
          <input
            {...a11y}
            type="text"
            inputMode="decimal"
            autoComplete="off"
            className={styles.input}
            value={draft ?? value}
            disabled={disabled}
            required={field.required}
            onChange={(e) => edit(e.target.value)}
            onBlur={blur}
          />
          {unit && (
            <span id={unitId} className={own.unit}>
              {unit}
            </span>
          )}
        </span>
      )}
    </Field>
  );
}
