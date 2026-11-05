import { Field } from "../Field/Field";
import styles from "../Field/Field.module.css";
import { formatInstant } from "./format";

export type DateTimeFieldProps = {
  id: string;
  label: string;
  /** ISO 8601 instant ending in Z, or "". */
  valueUtc: string;
  onChange: (isoUtc: string) => void;
  /** IANA zone; when set, the port-local time is shown below the field. */
  timeZone?: string;
  error?: string;
  required?: boolean;
  disabled?: boolean;
};

export function DateTimeField({
  id,
  label,
  valueUtc,
  onChange,
  timeZone,
  disabled,
  ...field
}: DateTimeFieldProps) {
  const hint = valueUtc && timeZone ? formatInstant(valueUtc, timeZone) : undefined;
  return (
    <Field id={id} label={`${label} (UTC)`} hint={hint} {...field}>
      {(a11y) => (
        <input
          {...a11y}
          type="datetime-local"
          className={styles.input}
          value={valueUtc.slice(0, 16)}
          disabled={disabled}
          required={field.required}
          onChange={(e) => onChange(e.target.value ? `${e.target.value}:00.000Z` : "")}
        />
      )}
    </Field>
  );
}
