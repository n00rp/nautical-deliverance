import { useCallback } from "react";
import { ApiError } from "../api";
import { useToast } from "../ui/Toast/Toast";

const CONFLICT = "Record was changed by someone else — reloaded the latest version";

const EXPIRED = "Session expired — sign in again";

export function describe(e: unknown): string {
  if (e instanceof ApiError && e.status === 409) return CONFLICT;
  if (e instanceof ApiError && e.status === 401) return EXPIRED;
  if (e instanceof ApiError && e.status === 403) return "You are not allowed to change this record";
  return e instanceof Error ? e.message : "Unknown error";
}

/** Toast for a failed call; a 409 also reloads the record so the user sees the latest version. */
export function useFail(reload: () => void) {
  const toast = useToast();
  return useCallback(
    (e: unknown) => {
      const conflict = e instanceof ApiError && e.status === 409;
      toast(describe(e), conflict ? "warn" : "crit");
      if (conflict) reload();
    },
    [toast, reload],
  );
}
