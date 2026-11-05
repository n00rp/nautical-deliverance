import { useId, type KeyboardEvent, type ReactNode } from "react";
import { Button } from "../Button/Button";
import panel from "../Panel/Panel.module.css";
import styles from "./DetailPanel.module.css";

export type DetailPanelProps = {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
};

/** Non-modal side panel: beside the content from 900 px, stacked below on narrow screens. */
export function DetailPanel({ title, open, onClose, children }: DetailPanelProps) {
  const titleId = useId();
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
