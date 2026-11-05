import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, type FieldIssue } from "../api";

/**
 * Submit state shared by the edit forms: busy, field errors (422), a forbidden flag (403), and
 * focus put back on the submit button, which is disabled while busy. Anything else goes to `onFail`.
 */
export function useSave(onFail: (e: unknown) => void) {
  const form = useRef<HTMLFormElement>(null);
  const refocus = useRef(false);
  const [issues, setIssues] = useState<FieldIssue[]>([]);
  const [forbidden, setForbidden] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (busy || !refocus.current) return;
    refocus.current = false;
    form.current?.querySelector<HTMLElement>("button[type=submit]")?.focus();
  }, [busy]);

  /** Drops the error of a field the user has just edited. */
  const clear = (match: (field: string) => boolean) => {
    setIssues((all) => all.filter((i) => !match(i.field)));
  };

  const submit = (run: () => Promise<void>) => async (e: FormEvent) => {
    e.preventDefault();
    refocus.current = form.current?.contains(document.activeElement) ?? false;
    setBusy(true);
    try {
      await run();
      setIssues([]);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) setIssues(err.issues);
      else if (err instanceof ApiError && err.status === 403) setForbidden(true);
      else onFail(err);
    } finally {
      setBusy(false);
    }
  };
  return { form, issues, clear, forbidden, setForbidden, busy, submit };
}
