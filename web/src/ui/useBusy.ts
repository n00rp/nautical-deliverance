import { useRef, useState } from "react";

/**
 * One call at a time: `guarded` ignores a call while another is running and tracks `pending` for
 * disabling buttons. Errors pass through to the caller.
 */
export function useBusy() {
  const [pending, setPending] = useState(false);
  const busy = useRef(false);
  const guarded = async (call: () => Promise<unknown>) => {
    if (busy.current) return;
    busy.current = true;
    setPending(true);
    try {
      await call();
    } finally {
      busy.current = false;
      setPending(false);
    }
  };
  return { pending, guarded };
}
