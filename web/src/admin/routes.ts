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

export const go = (sub: string) => {
  window.location.hash = `#/admin/${sub}`;
};
