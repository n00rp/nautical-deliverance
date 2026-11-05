import { ApiError, type FieldIssue } from "./api";
import type { HistoryEntry } from "./ui/HistoryList/HistoryList";

/** Where the client gets its bearer token: the current one per request, and a renewed one. */
export type TokenSource = {
  token: () => Promise<string>;
  /** Silent sign-in; resolves to the new access token, or null when there is none. */
  renew: () => Promise<string | null>;
};

export type RawHistory = Omit<HistoryEntry, "changes"> & {
  changes: Record<string, { before: string | null; after: string | null }>;
};

const isIssues = (v: unknown): v is FieldIssue[] =>
  Array.isArray(v) &&
  v.every((i: unknown) => typeof (i as FieldIssue | null)?.message === "string");

async function failure(response: Response): Promise<ApiError> {
  const body: unknown = await response.json().catch(() => null);
  const detail = (body as { detail?: unknown } | null)?.detail;
  return new ApiError(response.status, isIssues(detail) ? detail : []);
}

/** Audit entries as the engine returns them, reshaped for HistoryList. */
export const toHistory = (raw: RawHistory[]): HistoryEntry[] =>
  raw.map((e) => ({
    ...e,
    changes: Object.entries(e.changes).map(([field, c]) => ({ field, ...c })),
  }));

/** One JSON request helper for /api/v1/<path>. A 401 triggers one renewal and one retry. */
export function createRequest(auth: TokenSource) {
  const root = `${import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, "")}/api/v1`;

  const send = (method: string, path: string, token: string, body?: unknown) =>
    fetch(`${root}/${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });

  return async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
    let response = await send(method, path, await auth.token(), body);
    if (response.status === 401) {
      const fresh = await auth.renew().catch(() => null);
      if (fresh) response = await send(method, path, fresh, body);
    }
    if (!response.ok) throw await failure(response);
    return (await response.json()) as T;
  };
}
