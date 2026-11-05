import { useEffect, useState } from "react";
import { ApiError } from "../api";
import type { Rec, SetItem } from "../masterApi";
import { Button } from "../ui/Button/Button";
import { Checkbox } from "../ui/Checkbox/Checkbox";
import { EmptyState } from "../ui/EmptyState/EmptyState";
import { InlineConfirm } from "../ui/InlineConfirm/InlineConfirm";
import { Panel } from "../ui/Panel/Panel";
import { RoleGate } from "../ui/RoleGate/RoleGate";
import { StatusPill } from "../ui/StatusPill/StatusPill";
import { Table } from "../ui/Table/Table";
import { useToast } from "../ui/Toast/Toast";
import css from "./Admin.module.css";
import { EditForm, initialValues } from "./EditForm";
import type { ExtraCtx, FieldDef } from "./types";

const CONTACT_FIELDS: FieldDef[] = [
  { key: "name", label: "Name", kind: "text", required: true },
  { key: "email", label: "E-mail", kind: "text", required: true },
  { key: "phone", label: "Phone", kind: "text" },
  { key: "is_primary", label: "Primary contact", kind: "bool" },
];

/** Contacts of the open counterparty: list, add, edit, deactivate/reactivate. */
export function ContactsPanel({ ctx }: { ctx: ExtraCtx }) {
  const { api, rec, roles, onFail } = ctx;
  const [list, setList] = useState<Rec[]>([]);
  const [editing, setEditing] = useState<Rec | null>(null);
  const [tick, setTick] = useState(0);
  const refresh = () => {
    setTick((t) => t + 1);
  };

  useEffect(() => {
    let live = true;
    api.contacts(rec.id).then((r) => {
      if (live) setList(r);
    }, onFail);
    return () => {
      live = false;
    };
  }, [api, rec.id, onFail, tick]);

  const toggle = (c: Rec, on: boolean) => {
    api.setContactActive(rec.id, c.id, c.version, on).then(refresh, (e: unknown) => {
      onFail(e);
      refresh();
    });
  };

  return (
    <Panel title="Contacts">
      <div className={css.stack}>
        <Table
          caption="Contacts"
          rows={list}
          rowKey={(c) => c.id}
          empty="No contacts yet"
          columns={[
            { key: "name", header: "Name", render: (c) => String(c.name) },
            { key: "email", header: "E-mail", render: (c) => String(c.email) },
            { key: "phone", header: "Phone", render: (c) => String(c.phone ?? "—") },
            { key: "primary", header: "Primary", render: (c) => (c.is_primary ? "Yes" : "—") },
            {
              key: "status",
              header: "Status",
              render: (c) => (c.active ? null : <StatusPill tone="warn">Inactive</StatusPill>),
            },
            {
              key: "actions",
              header: "Actions",
              render: (c) => (
                <RoleGate allow={["admin"]} roles={roles}>
                  <span className={css.actions}>
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setEditing(c);
                      }}
                    >
                      Edit
                    </Button>
                    {c.active ? (
                      <InlineConfirm
                        label="Deactivate"
                        confirmLabel="Confirm deactivate"
                        tone="crit"
                        onConfirm={() => {
                          toggle(c, false);
                        }}
                      />
                    ) : (
                      <Button
                        variant="secondary"
                        onClick={() => {
                          toggle(c, true);
                        }}
                      >
                        Reactivate
                      </Button>
                    )}
                  </span>
                </RoleGate>
              ),
            },
          ]}
        />
        <RoleGate allow={["admin"]} roles={roles}>
          <EditForm
            key={editing ? `${editing.id}:${String(editing.version)}` : `new${String(tick)}`}
            name="Contact"
            wide
            fields={CONTACT_FIELDS}
            initial={initialValues(CONTACT_FIELDS, editing ?? undefined)}
            refs={{}}
            roles={roles}
            submitLabel={editing ? "Save contact" : "Add contact"}
            onFail={onFail}
            onCancel={
              editing
                ? () => {
                    setEditing(null);
                  }
                : undefined
            }
            onSubmit={async (body) => {
              try {
                await (editing
                  ? api.updateContact(rec.id, editing.id, editing.version, body)
                  : api.addContact(rec.id, body));
              } catch (e) {
                if (e instanceof ApiError && e.status === 409) refresh();
                throw e;
              }
              setEditing(null);
              refresh();
            }}
          />
        </RoleGate>
      </div>
    </Panel>
  );
}

export type SetSpec = {
  title: string;
  saveLabel: string;
  saved: string;
  url: (id: string) => string;
  /** Row type (ports); without it the set is a single list of checkboxes. */
  rows?: "ports";
  rowHeader?: string;
  cols: "products";
  item: (rowId: string, colId: string) => SetItem;
};

type Named = { id: string; name: string };
const keyOf = (item: SetItem) => Object.values(item).join(":");
const named = (r: Rec): Named => ({ id: r.id, name: String(r.name) });
const SINGLE: Named[] = [{ id: "", name: "" }];

/** Replace-the-set editor: coverage matrix (ports x products) or approved fuels (products). */
export function SetPanel({ ctx, spec }: { ctx: ExtraCtx; spec: SetSpec }) {
  const { api, rec, refs, roles, onFail, reload, epoch } = ctx;
  const toast = useToast();
  const url = spec.url(rec.id);
  // `saved` is the server's set; null until it has loaded (Save stays off, so an empty
  // draft can never overwrite a set that has not been read).
  const [saved, setSaved] = useState<SetItem[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const rows = spec.rows ? (refs[spec.rows] ?? []).map(named) : SINGLE;
  const cols = (refs[spec.cols] ?? []).map(named);
  const load = (s: { items: SetItem[] }) => {
    setSaved(s.items);
    setSelected(new Set(s.items.map(keyOf)));
  };

  // Not keyed on the record version: saving the details must not reset ticks in progress.
  useEffect(() => {
    let live = true;
    api.getSet(url).then((s) => {
      if (live) load(s);
    }, onFail);
    return () => {
      live = false;
    };
  }, [api, url, epoch, onFail]);

  const cell = (r: Named, c: Named) => {
    const key = keyOf(spec.item(r.id, c.id));
    return (
      <Checkbox
        id={`${spec.title}-${r.id}-${c.id}`}
        label={r.name ? `${r.name} – ${c.name}` : c.name}
        hideLabel={Boolean(spec.rows)}
        checked={selected.has(key)}
        disabled={!roles.includes("admin")}
        onChange={(on) => {
          setSelected((s) => {
            const next = new Set(s);
            if (on) next.add(key);
            else next.delete(key);
            return next;
          });
        }}
      />
    );
  };

  const dirty =
    saved !== null &&
    (selected.size !== saved.length || saved.some((i) => !selected.has(keyOf(i))));

  const save = () => {
    if (!saved) return;
    const shown = rows.flatMap((r) => cols.map((c) => spec.item(r.id, c.id)));
    const shownKeys = new Set(shown.map(keyOf));
    // Entries on inactive ports/products are not drawn; they are carried through unchanged.
    const items = [
      ...shown.filter((i) => selected.has(keyOf(i))),
      ...saved.filter((i) => !shownKeys.has(keyOf(i))),
    ];
    api.putSet(url, rec.version, items).then((s) => {
      load(s);
      toast(spec.saved, "ok");
      reload();
    }, onFail);
  };

  return (
    <Panel title={spec.title}>
      <div className={css.stack}>
        {rows.length === 0 || cols.length === 0 ? (
          <EmptyState title="Nothing to choose from" body="Add ports and products first." />
        ) : spec.rows ? (
          <Table
            caption={spec.title}
            rows={rows}
            rowKey={(r) => r.id}
            columns={[
              { key: "row", header: spec.rowHeader ?? "", render: (r) => r.name },
              ...cols.map((c) => ({
                key: c.id,
                header: c.name,
                render: (r: Named) => cell(r, c),
              })),
            ]}
          />
        ) : (
          <div className={css.checks}>{cols.map((c) => cell({ id: "", name: "" }, c))}</div>
        )}
        <RoleGate allow={["admin"]} roles={roles}>
          <div className={css.actions}>
            <Button variant="primary" onClick={save} disabled={!dirty}>
              {spec.saveLabel}
            </Button>
          </div>
        </RoleGate>
      </div>
    </Panel>
  );
}
