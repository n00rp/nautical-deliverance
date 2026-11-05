import type { ReactNode } from "react";
import styles from "./StatusPill.module.css";

type Tone = "ok" | "warn" | "crit" | "info" | "accent";
type Status =
  "Draft" | "RFQ sent" | "Offers received" | "Winner selected" | "Nominated" | "Cancelled";

const STATUS_TONE: Record<Status, Tone> = {
  Draft: "info",
  "RFQ sent": "info",
  "Offers received": "info",
  "Winner selected": "accent",
  Nominated: "ok",
  Cancelled: "crit",
};

export type StatusPillProps = { status: Status } | { tone: Tone; children: ReactNode };

export function StatusPill(props: StatusPillProps) {
  const tone = "status" in props ? STATUS_TONE[props.status] : props.tone;
  return (
    <span className={styles.pill} data-tone={tone}>
      {"status" in props ? props.status : props.children}
    </span>
  );
}
