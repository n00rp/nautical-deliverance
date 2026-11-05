import type { ReactNode } from "react";
import styles from "./FieldError.module.css";

export function FieldError({ id, children }: { id: string; children: ReactNode }) {
  return (
    <p id={id} role="alert" className={styles.error}>
      {children}
    </p>
  );
}
