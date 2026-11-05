import { useState } from "react";
import { Button } from "../Button/Button";
import styles from "./InlineConfirm.module.css";

export type InlineConfirmProps = {
  label: string;
  confirmLabel: string;
  onConfirm: () => void;
  tone?: "default" | "crit";
};

export function InlineConfirm({
  label,
  confirmLabel,
  onConfirm,
  tone = "default",
}: InlineConfirmProps) {
  const [armed, setArmed] = useState(false);
  if (!armed) {
    return (
      <Button variant="secondary" onClick={() => setArmed(true)}>
        {label}
      </Button>
    );
  }
  return (
    <span className={styles.row} data-tone={tone}>
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
