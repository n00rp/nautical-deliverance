import { ApiError, type FieldIssue } from "./api";
import type { HistoryEntry } from "./ui/HistoryList/HistoryList";

export type MasterType =
  | "legal-entities"
  | "vessels"
  | "ports"
  | "counterparties"
  | "products"
  | "iso-spec-versions"
  | "bunkering-reasons";

type Value = string | number | boolean | null;
export type Body = Record<string, Value>;
/** A master record as the engine returns it: its own fields plus id, active and version. */
export type Rec = { id: string; active: boolean; version: number } & Record<string, Value>;
/** One member of a replace-the-set child list, e.g. `{port_id, product_id}`. */
export type SetItem = Record<string, string>;
export type SetState = { version: number; items: SetItem[] };
export type ActiveFilter = "true" | "false" | "all";

type RawHistory = Omit<HistoryEntry, "changes"> & {
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

/** Where the client gets its bearer token: the current one per request, and a renewed one. */
export type TokenSource = {
  token: () => Promise<string>;
  /** Silent sign-in; resolves to the new access token, or null when there is none. */
  renew: () => Promise<string | null>;
};

/** Typed client for /api/v1/master. A 401 triggers one renewal and one retry. */
export function createMasterApi(auth: TokenSource) {
  const root = `${import.meta.env.VITE_API_BASE_URL.replace(/\/+$/, "")}/api/v1/master`;

  const send = (method: string, path: string, token: string, body?: unknown) =>
    fetch(`${root}/${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });

  async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
    let response = await send(method, path, await auth.token(), body);
    if (response.status === 401) {
      const fresh = await auth.renew().catch(() => null);
      if (fresh) response = await send(method, path, fresh, body);
    }
    if (!response.ok) throw await failure(response);
    return (await response.json()) as T;
  }

  const active = (on: boolean) => (on ? "reactivate" : "deactivate");
  const enc = encodeURIComponent;
  const contacts = (cp: string) => `counterparties/${enc(cp)}/contacts`;

  return {
    list: (type: MasterType, filter: ActiveFilter, q?: string) =>
      call<Rec[]>("GET", `${type}?${new URLSearchParams({ active: filter, ...(q ? { q } : {}) })}`),
    get: (type: MasterType, id: string) => call<Rec>("GET", `${type}/${enc(id)}`),
    create: (type: MasterType, body: Body) => call<Rec>("POST", type, body),
    update: (type: MasterType, id: string, version: number, body: Body) =>
      call<Rec>("PATCH", `${type}/${enc(id)}`, { ...body, version }),
    setActive: (type: MasterType, id: string, version: number, on: boolean) =>
      call<Rec>("POST", `${type}/${enc(id)}/${active(on)}`, { version }),
    async history(type: MasterType, id: string): Promise<HistoryEntry[]> {
      const raw = await call<RawHistory[]>("GET", `${type}/${enc(id)}/history`);
      return raw.map((e) => ({
        ...e,
        changes: Object.entries(e.changes).map(([field, c]) => ({ field, ...c })),
      }));
    },
    contacts: (cp: string) => call<Rec[]>("GET", `${contacts(cp)}?active=all`),
    addContact: (cp: string, body: Body) => call<Rec>("POST", contacts(cp), body),
    updateContact: (cp: string, id: string, version: number, body: Body) =>
      call<Rec>("PATCH", `${contacts(cp)}/${enc(id)}`, { ...body, version }),
    setContactActive: (cp: string, id: string, version: number, on: boolean) =>
      call<Rec>("POST", `${contacts(cp)}/${enc(id)}/${active(on)}`, { version }),
    /** `path` is e.g. `counterparties/<id>/coverage` or `vessels/<id>/approved-fuels`. */
    getSet: (path: string) => call<SetState>("GET", path),
    putSet: (path: string, version: number, items: SetItem[]) =>
      call<SetState>("PUT", path, { version, items }),
  };
}

export type MasterApi = ReturnType<typeof createMasterApi>;
