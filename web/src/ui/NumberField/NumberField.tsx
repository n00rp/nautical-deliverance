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
  /** Called with false while the text is not a valid number (value is then ""), true again after. */
  onValidityChange?: (valid: boolean) => void;
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
  onValidityChange,
  unit,
  disabled,
  error,
  ...field
}: NumberFieldProps) {
  // `draft` is what the user typed; null means "show the committed value".
  const [draft, setDraft] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | undefined>();

  // The parent changed the value to something the draft does not mean (e.g. a form reset).
  const parsed = draft === null ? null : normalizeDecimal(draft, decimals);
  const stale = parsed !== null && ("value" in parsed ? parsed.value !== value : value !== "");
  if (stale) {
    setDraft(null);
    setLocalError(undefined);
  }

  const edit = (raw: string) => {
    setDraft(raw);
    const r = normalizeDecimal(raw, decimals);
    if ("value" in r) {
      setLocalError(undefined);
      onChange(r.value);
      onValidityChange?.(true);
    } else {
      // Never leave a stale value with the parent: clear it and say the input is invalid.
      // A trailing separator is merely unfinished, so its message waits for blur.
      setLocalError(/[.,]$/.test(raw) ? undefined : r.error);
      onChange("");
      onValidityChange?.(false);
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
            value={stale ? value : (draft ?? value)}
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
