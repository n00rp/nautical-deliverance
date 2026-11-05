import type { ReactNode } from "react";
import styles from "./EmptyState.module.css";

export type EmptyStateProps = { title: string; body?: string; action?: ReactNode };

export function EmptyState({ title, body, action }: EmptyStateProps) {
  return (
    <div className={styles.empty}>
      <p className={styles.title}>{title}</p>
      {body && <p className={styles.body}>{body}</p>}
      {action}
    </div>
  );
}
