import { formatInstant } from "../DateTimeField/format";
import styles from "./HistoryList.module.css";

export type HistoryEntry = {
  id: string;
  actor: string;
  at: string;
  /** Label of a related record this entry is about, e.g. "Contact Ann". */
  entity?: string | null;
  action: "create" | "update" | "deactivate" | "reactivate";
  changes: { field: string; before: string | null; after: string | null }[];
};

const VERB = {
  create: "created",
  update: "updated",
  deactivate: "deactivated",
  reactivate: "reactivated",
} as const;

const show = (v: string | null) => v ?? "—";

export function HistoryList({ entries }: { entries: HistoryEntry[] }) {
  if (entries.length === 0) return <p className={styles.none}>No history yet</p>;
  // An unparseable timestamp counts as oldest, so the comparator never sees NaN.
  const time = (at: string) => Date.parse(at) || 0;
  const newestFirst = [...entries].sort((a, b) => time(b.at) - time(a.at));
  return (
    <ol className={styles.list}>
      {newestFirst.map((e) => (
        <li key={e.id} data-entry={e.id} className={styles.entry}>
          <p className={styles.head}>
            <strong>{e.actor}</strong> {VERB[e.action]} {e.entity && <em>{e.entity} </em>}
            <time dateTime={e.at} className={styles.time}>
              {formatInstant(e.at)}
            </time>
          </p>
          {e.changes.length > 0 && (
            <ul className={styles.changes}>
              {e.changes.map((c) => (
                <li key={c.field}>
                  <span className={styles.field}>{c.field}</span>{" "}
                  <span>{`${show(c.before)} → ${show(c.after)}`}</span>
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ol>
  );
}
