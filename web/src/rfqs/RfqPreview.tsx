import { useEffect, useRef, useState, type ReactNode } from "react";
import { describe } from "../admin/errors";
import type { RfqApi, RfqItem, RfqPreview as Preview } from "../rfqApi";
import { Button } from "../ui/Button/Button";
import { useToast } from "../ui/Toast/Toast";
import css from "./RfqLog.module.css";

export type RfqPreviewProps = {
  rfq: RfqItem;
  api: Pick<RfqApi, "getPreview">;
  /** Rendered under the preview (the status actions). */
  children?: ReactNode;
};

/** The exact message that would be mailed, with the mail link and Copy text (B3-R12). */
export function RfqPreview({ rfq, api, children }: RfqPreviewProps) {
  const toast = useToast();
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const body = useRef<HTMLPreElement>(null);

  // The message depends on the contact and deadline, which move the version.
  useEffect(() => {
    let live = true;
    setPreview(null);
    setError(null);
    api.getPreview(rfq.id).then(
      (p) => {
        if (live) setPreview(p);
      },
      (e: unknown) => {
        if (live) setError(describe(e));
      },
    );
    return () => {
      live = false;
    };
  }, [api, rfq.id, rfq.version]);

  if (error) return <p role="alert">{error}</p>;
  if (!preview) return <p role="status">Loading…</p>;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(preview.body);
      toast("Copied", "ok");
    } catch {
      // No clipboard access: select the text so Ctrl+C works.
      if (body.current) window.getSelection()?.selectAllChildren(body.current);
      toast("Could not copy — the text is selected, press Ctrl+C", "warn");
    }
  };

  return (
    <div className={css.preview}>
      <dl className={css.message}>
        <dt>To</dt>
        <dd>{preview.to}</dd>
        <dt>Subject</dt>
        <dd>{preview.subject}</dd>
        <dt>Body</dt>
        <dd>
          <pre ref={body} className={css.body}>
            {preview.body}
          </pre>
        </dd>
      </dl>
      <div className={css.actions}>
        <a className={css.mail} href={preview.mailto}>
          Open in e-mail
        </a>
        <Button variant="secondary" onClick={() => void copy()}>
          Copy text
        </Button>
      </div>
      {!preview.body_in_link && (
        <p className={css.note}>Body too long for a mail link — use Copy text</p>
      )}
      {children}
    </div>
  );
}
