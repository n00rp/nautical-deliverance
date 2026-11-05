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
};

export function TextField({ id, label, value, onChange, disabled, ...field }: TextFieldProps) {
  return (
    <Field id={id} label={label} {...field}>
      {(a11y) => (
        <input
          {...a11y}
          type="text"
          className={styles.input}
          value={value}
          disabled={disabled}
          required={field.required}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </Field>
  );
}
