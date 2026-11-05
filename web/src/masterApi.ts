import { createRequest, toHistory, type RawHistory, type TokenSource } from "./http";

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

/** Typed client for /api/v1/master. A 401 triggers one renewal and one retry. */
export function createMasterApi(auth: TokenSource) {
  const request = createRequest(auth);
  const call = <T>(method: string, path: string, body?: unknown) =>
    request<T>(method, `master/${path}`, body);

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
    history: async (type: MasterType, id: string) =>
      toHistory(await call<RawHistory[]>("GET", `${type}/${enc(id)}/history`)),
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
