import { useEffect, useState } from "react";
import { useToast } from "../ui/Toast/Toast";
import { describe } from "./errors";

/**
 * Runs `load` when `enabled` and whenever `deps` change; a failure toasts and sets `failed`.
 * A result that arrives after the inputs changed (or after unmount) is dropped.
 */
export function useLoaded<T>(enabled: boolean, load: () => Promise<T>, deps: readonly unknown[]) {
  const toast = useToast();
  const [data, setData] = useState<T | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    load().then(
      (d) => {
        if (live) setData(d);
      },
      (e: unknown) => {
        if (!live) return;
        setFailed(true);
        toast(describe(e), "crit");
      },
    );
    return () => {
      live = false;
    };
    // `load` is a fresh closure every render; `deps` says when its inputs changed.
  }, [enabled, toast, ...deps]);
  return { data, failed };
}
