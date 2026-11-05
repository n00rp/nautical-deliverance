// In-memory stand-in for the master-data API, shared by the page tests and the stories.
import { ApiError } from "../api";
import type { MasterApi, MasterType, Rec, SetItem } from "../masterApi";
import type { HistoryEntry } from "../ui/HistoryList/HistoryList";

type Seed = Partial<Record<MasterType, Rec[]>>;
type SetState = { items: SetItem[] };

export const rec = (id: string, fields: Record<string, string | number | boolean | null>): Rec => ({
  id,
  active: true,
  version: 1,
  ...fields,
});

export function fakeApi(
  seed: Seed = {},
  sets: Record<string, SetItem[]> = {},
  contacts: Rec[] = [],
) {
  const store = new Map<MasterType, Rec[]>(Object.entries(seed) as [MasterType, Rec[]][]);
  const logs = new Map<string, HistoryEntry[]>();
  const setStore = new Map<string, SetState>(
    Object.entries(sets).map(([path, items]) => [path, { items }]),
  );
  const contactStore = [...contacts];
  let next = 1;
  const rows = (type: MasterType) => store.get(type) ?? [];
  const find = (type: MasterType, id: string) => {
    const row = rows(type).find((r) => r.id === id);
    if (!row) throw new ApiError(404);
    return row;
  };
  const log = (id: string, action: HistoryEntry["action"], fields: string[]) => {
    const entry: HistoryEntry = {
      id: `h${String(next++)}`,
      actor: "tester",
      at: new Date(Date.UTC(2026, 10, 5, 10, next)).toISOString(),
      action,
      changes: fields.map((field) => ({ field, before: null, after: "x" })),
    };
    logs.set(id, [entry, ...(logs.get(id) ?? [])]);
  };
  const change = (
    row: Rec,
    version: number,
    patch: Partial<Rec>,
    action: HistoryEntry["action"],
  ) => {
    if (row.version !== version) throw new ApiError(409);
    Object.assign(row, patch, { version: row.version + 1 });
    log(row.id, action, Object.keys(patch));
    return { ...row };
  };
  const api: MasterApi = {
    list: (type, active, q) =>
      Promise.resolve(
        rows(type)
          .filter((r) => active === "all" || r.active === (active === "true"))
          .filter((r) => !q || String(r.name).toLowerCase().includes(q.toLowerCase()))
          .map((r) => ({ ...r })),
      ),
    get: (type, id) => Promise.resolve({ ...find(type, id) }),
    create: (type, body) => {
      const row = rec(`${type}-${String(next++)}`, body);
      store.set(type, [...rows(type), row]);
      log(row.id, "create", Object.keys(body));
      return Promise.resolve({ ...row });
    },
    update: (type, id, version, body) =>
      Promise.resolve(change(find(type, id), version, body, "update")),
    setActive: (type, id, version, active) =>
      Promise.resolve(
        change(find(type, id), version, { active }, active ? "reactivate" : "deactivate"),
      ),
    history: (type, id) => Promise.resolve(logs.get(find(type, id).id) ?? []),
    contacts: () => Promise.resolve(contactStore.map((c) => ({ ...c }))),
    addContact: (_, body) => {
      const row = rec(`c${String(next++)}`, body);
      contactStore.push(row);
      return Promise.resolve({ ...row });
    },
    updateContact: (_, id, version, body) => {
      const row = contactStore.find((c) => c.id === id);
      if (!row) throw new ApiError(404);
      return Promise.resolve(change(row, version, body, "update"));
    },
    setContactActive: (_, id, version, active) => {
      const row = contactStore.find((c) => c.id === id);
      if (!row) throw new ApiError(404);
      return Promise.resolve(change(row, version, { active }, "update"));
    },
    getSet: (path) => {
      const parent = parentOf(path);
      return Promise.resolve({
        version: find(parent.type, parent.id).version,
        items: setStore.get(path)?.items ?? [],
      });
    },
    putSet: (path, version, items) => {
      const parent = parentOf(path);
      const row = find(parent.type, parent.id);
      change(row, version, {}, "update");
      setStore.set(path, { items });
      return Promise.resolve({ version: row.version, items });
    },
  };
  return Object.assign(api, { sets: setStore, contactsNow: contactStore, rows });
}

function parentOf(path: string): { type: MasterType; id: string } {
  const [type, id] = path.split("/");
  return { type: type as MasterType, id: id ?? "" };
}
