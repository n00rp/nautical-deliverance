import { useEffect, useRef, useState } from "react";
import { Button } from "../Button/Button";
import styles from "./InlineConfirm.module.css";

export type InlineConfirmProps = {
  label: string;
  confirmLabel: string;
  onConfirm: () => void;
  disabled?: boolean;
  tone?: "default" | "crit";
  /** Armed state resets after this many ms. */
  timeoutMs?: number;
};

export function InlineConfirm({
  label,
  confirmLabel,
  onConfirm,
  disabled = false,
  tone = "default",
  timeoutMs = 8000,
}: InlineConfirmProps) {
  const [armed, setArmed] = useState(false);
  const row = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!armed) return;
    row.current?.querySelector("button")?.focus();
    const t = setTimeout(() => {
      setArmed(false);
    }, timeoutMs);
    return () => {
      clearTimeout(t);
    };
  }, [armed, timeoutMs]);
  if (!armed) {
    return (
      <Button variant="secondary" disabled={disabled} onClick={() => setArmed(true)}>
        {label}
      </Button>
    );
  }
  return (
    <span
      ref={row}
      className={styles.row}
      data-tone={tone}
      onBlur={(e) => {
        if (!row.current?.contains(e.relatedTarget)) setArmed(false);
      }}
    >
      <Button
        variant="primary"
        className={tone === "crit" ? styles.crit : undefined}
        onClick={() => {
          setArmed(false);
          onConfirm();
        }}
      >
        {confirmLabel}
      </Button>
      <Button variant="ghost" onClick={() => setArmed(false)}>
        Cancel
      </Button>
    </span>
  );
}
