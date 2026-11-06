import { useMemo, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import styles from "./Table.module.css";

type Column<Row> = {
  key: string;
  header: string;
  align?: "start" | "end";
  render: (row: Row) => ReactNode;
  sortValue?: (row: Row) => string | number;
};

export type TableProps<Row> = {
  columns: Column<Row>[];
  rows: Row[];
  rowKey: (row: Row) => string;
  onRowSelect?: (row: Row) => void;
  selectedKey?: string;
  /** Rows to draw with the highlight tone (e.g. the lowest offer). */
  highlight?: (row: Row) => boolean;
  loading?: boolean;
  empty?: ReactNode;
  caption: string;
};

const INTERACTIVE = "button, a, input, select, textarea, label";

type Sort = { key: string; dir: "ascending" | "descending" } | null;

const compare = (a: string | number, b: string | number) =>
  typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b));

export function Table<Row>({
  columns,
  rows,
  rowKey,
  onRowSelect,
  selectedKey,
  highlight,
  loading = false,
  empty = "Nothing to show",
  caption,
}: TableProps<Row>) {
  const [sort, setSort] = useState<Sort>(null);

  const sorted = useMemo(() => {
    const col = columns.find((c) => c.key === sort?.key);
    if (!sort || !col?.sortValue) return rows;
    const value = col.sortValue;
    const sign = sort.dir === "ascending" ? 1 : -1;
    // Array.prototype.sort is stable, so equal values keep their input order.
    return [...rows].sort((a, b) => sign * compare(value(a), value(b)));
  }, [columns, rows, sort]);

  const toggle = (key: string) =>
    setSort((s) =>
      s?.key !== key
        ? { key, dir: "ascending" }
        : s.dir === "ascending"
          ? { key, dir: "descending" }
          : null,
    );

  const onClick = (e: MouseEvent<HTMLTableRowElement>, row: Row) => {
    const inner = (e.target as Element).closest(INTERACTIVE);
    if (inner && inner !== e.currentTarget && e.currentTarget.contains(inner)) return;
    onRowSelect?.(row);
  };

  const onKeyDown = (e: KeyboardEvent, row: Row) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onRowSelect?.(row);
    }
  };

  const message = loading ? "Loading…" : rows.length === 0 ? empty : null;

  return (
    <div className={styles.scroll} data-scroll>
      <table className={styles.table} aria-busy={loading || undefined}>
        <caption className={styles.caption}>{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                scope="col"
                data-align={c.align ?? "start"}
                aria-sort={sort?.key === c.key ? sort.dir : undefined}
              >
                {c.sortValue ? (
                  <button type="button" className={styles.sort} onClick={() => toggle(c.key)}>
                    {c.header}
                  </button>
                ) : (
                  c.header
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {message !== null ? (
            <tr>
              <td colSpan={columns.length} className={styles.message}>
                <span role="status">{message}</span>
              </td>
            </tr>
          ) : (
            sorted.map((row) => {
              const key = rowKey(row);
              return (
                <tr
                  key={key}
                  className={onRowSelect ? styles.selectable : undefined}
                  data-highlight={highlight?.(row) || undefined}
                  tabIndex={onRowSelect ? 0 : undefined}
                  aria-selected={onRowSelect ? key === selectedKey : undefined}
                  onClick={onRowSelect && ((e) => onClick(e, row))}
                  onKeyDown={onRowSelect && ((e) => onKeyDown(e, row))}
                >
                  {columns.map((c) => (
                    <td key={c.key} data-align={c.align ?? "start"}>
                      {c.render(row)}
                    </td>
                  ))}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
