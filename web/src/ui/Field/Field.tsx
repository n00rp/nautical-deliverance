import type { ReactNode } from "react";
import { FieldError } from "../FieldError/FieldError";
import styles from "./Field.module.css";

type ControlA11y = {
  id: string;
  "aria-describedby": string | undefined;
  "aria-invalid": true | undefined;
  "aria-required": true | undefined;
};

export type FieldProps = {
  id: string;
  label: string;
  hint?: string | undefined;
  error?: string | undefined;
  required?: boolean | undefined;
  /** Extra element id (e.g. a unit) the control is described by. */
  describedBy?: string | undefined;
  children: (a11y: ControlA11y) => ReactNode;
};

/** Shared label / control / hint / error wiring for the form fields. */
export function Field({ id, label, hint, error, required, describedBy, children }: FieldProps) {
  const ids = [hint ? `${id}-hint` : "", error ? `${id}-error` : "", describedBy ?? ""]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={styles.field}>
      <label htmlFor={id} className={styles.label}>
        {label}
        {required && <span aria-hidden="true"> *</span>}
      </label>
      {children({
        id,
        "aria-describedby": ids || undefined,
        "aria-invalid": error ? true : undefined,
        "aria-required": required ? true : undefined,
      })}
      {hint && (
        <p id={`${id}-hint`} className={styles.hint}>
          {hint}
        </p>
      )}
      {error && <FieldError id={`${id}-error`}>{error}</FieldError>}
    </div>
  );
}
