import { Field } from "../Field/Field";
import styles from "../Field/Field.module.css";

export type TextFieldProps = {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  hint?: string;
  required?: boolean;
  disabled?: boolean;
  /** Draws a text area of this many rows instead of a one-line input. */
  rows?: number;
  maxLength?: number;
};

export function TextField({
  id,
  label,
  value,
  onChange,
  disabled,
  rows,
  maxLength,
  ...field
}: TextFieldProps) {
  return (
    <Field id={id} label={label} {...field}>
      {(a11y) =>
        rows ? (
          <textarea
            {...a11y}
            rows={rows}
            className={styles.input}
            value={value}
            disabled={disabled}
            required={field.required}
            onChange={(e) => onChange(e.target.value)}
          />
        ) : (
          <input
            {...a11y}
            type="text"
            maxLength={maxLength}
            className={styles.input}
            value={value}
            disabled={disabled}
            required={field.required}
            onChange={(e) => onChange(e.target.value)}
          />
        )
      }
    </Field>
  );
}
