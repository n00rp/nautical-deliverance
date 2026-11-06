import { useSyncExternalStore } from "react";
import type { MasterType } from "../masterApi";
import { MASTER_CONFIGS } from "./configs";

const subscribe = (notify: () => void) => {
  window.addEventListener("hashchange", notify);
  return () => {
    window.removeEventListener("hashchange", notify);
  };
};

export const useHash = () => useSyncExternalStore(subscribe, () => window.location.hash);

/** `#/admin/<type>` or `#/admin/<type>/<id|new>`; null for anything else. */
export function parseAdmin(hash: string): { path: MasterType; id: string | undefined } | null {
  const m = /^#\/admin\/([a-z-]+)(?:\/([^/]+))?$/.exec(hash);
  const config = MASTER_CONFIGS.find((c) => c.path === m?.[1]);
  return config ? { path: config.path, id: m?.[2] } : null;
}

export type InquiryRoute = { id: string | undefined; view?: "suppliers" | "rfqs" };

/**
 * `#/inquiries`, `#/inquiries/<id|new>`, `#/inquiries/<id>/suppliers` or `/rfqs`; an empty hash,
 * `#/` and `#/inquiries/` are the start page.
 */
export function parseInquiries(hash: string): InquiryRoute | null {
  const path = hash.replace(/^#\/?/, "").replace(/\/$/, "");
  if (path === "") return { id: undefined };
  const m = /^inquiries(?:\/([^/]+)(?:\/(suppliers|rfqs))?)?$/.exec(path);
  if (!m) return null;
  return m[2] ? { id: m[1], view: m[2] as "suppliers" | "rfqs" } : { id: m[1] };
}

export const goInquiry = (sub: string) => {
  window.location.hash = `#/inquiries/${sub}`;
};

export const go = (sub: string) => {
  window.location.hash = `#/admin/${sub}`;
};
