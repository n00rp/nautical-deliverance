import { useId, type ReactNode } from "react";
import styles from "./Panel.module.css";

export type PanelProps = { title?: string; actions?: ReactNode; children: ReactNode };

export function Panel({ title, actions, children }: PanelProps) {
  const titleId = useId();
  return (
    <section className={styles.panel} aria-labelledby={title ? titleId : undefined}>
      {(title || actions) && (
        <header className={styles.head}>
          {title && (
            <h2 id={titleId} className={styles.title}>
              {title}
            </h2>
          )}
          {actions}
        </header>
      )}
      <div className={styles.body}>{children}</div>
    </section>
  );
}
