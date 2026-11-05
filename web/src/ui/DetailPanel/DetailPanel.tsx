import { useEffect, useId, type KeyboardEvent, type ReactNode, type RefObject } from "react";
import { Button } from "../Button/Button";
import panel from "../Panel/Panel.module.css";
import styles from "./DetailPanel.module.css";

export type DetailPanelProps = {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  /** Where focus goes on close; defaults to whatever had focus when the panel opened. */
  returnFocusRef?: RefObject<HTMLElement | null>;
};

/** Non-modal side panel: beside the content from 900 px, stacked below on narrow screens. */
export function DetailPanel({ title, open, onClose, children, returnFocusRef }: DetailPanelProps) {
  const titleId = useId();
  useEffect(() => {
    if (!open) return;
    const before = document.activeElement as HTMLElement | null;
    return () => (returnFocusRef?.current ?? before)?.focus();
  }, [open, returnFocusRef]);
  if (!open) return null;
  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape") onClose();
  };
  return (
    // Escape bubbles up from the focusable controls inside; the aside itself is not a control.
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <aside
      className={`${panel.panel} ${styles.side}`}
      aria-labelledby={titleId}
      onKeyDown={onKeyDown}
    >
      <header className={panel.head}>
        <h2 id={titleId} className={panel.title}>
          {title}
        </h2>
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
      </header>
      <div className={panel.body}>{children}</div>
    </aside>
  );
}
