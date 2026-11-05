import { useCallback, useEffect, useState } from "react";
import type { ActiveFilter, MasterApi, Rec } from "../masterApi";
import { Button } from "../ui/Button/Button";
import { DetailPanel } from "../ui/DetailPanel/DetailPanel";
import { EmptyState } from "../ui/EmptyState/EmptyState";
import { HistoryList, type HistoryEntry } from "../ui/HistoryList/HistoryList";
import { InlineConfirm } from "../ui/InlineConfirm/InlineConfirm";
import { Panel } from "../ui/Panel/Panel";
import { RoleGate, type Role } from "../ui/RoleGate/RoleGate";
import { Select } from "../ui/Select/Select";
import { StatusPill } from "../ui/StatusPill/StatusPill";
import { Table } from "../ui/Table/Table";
import { TextField } from "../ui/TextField/TextField";
import { useToast } from "../ui/Toast/Toast";
import css from "./Admin.module.css";
import { EditForm, initialValues } from "./EditForm";
import { describe, useFail } from "./errors";
import { go, parseAdmin, useHash } from "./routes";
import type { MasterConfig, Refs } from "./types";

export type MasterDataPageProps = { config: MasterConfig; api: MasterApi; roles: Role[] };

const FILTERS: { value: ActiveFilter; label: string }[] = [
  { value: "true", label: "Active" },
  { value: "false", label: "Inactive" },
  { value: "all", label: "All" },
];

/** One generic list + detail page for a master-data type (B1-R11). */
export function MasterDataPage({ config, api, roles }: MasterDataPageProps) {
  const route = parseAdmin(useHash());
  const id = route?.path === config.path ? route.id : undefined;
  const toast = useToast();
  const [filter, setFilter] = useState<ActiveFilter>("true");
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<Rec[] | null>(null);
  const [refs, setRefs] = useState<Refs>({});
  const [tick, setTick] = useState(0);
  const reloadList = useCallback(() => {
    setTick((t) => t + 1);
  }, []);

  useEffect(() => {
    let live = true;
    api.list(config.path, filter, q || undefined).then(
      (r) => {
        if (live) setRows(r);
      },
      (e: unknown) => {
        if (!live) return;
        setRows([]);
        toast(describe(e), "crit");
      },
    );
    return () => {
      live = false;
    };
  }, [api, config.path, filter, q, tick, toast]);

  useEffect(() => {
    let live = true;
    Promise.all(config.refs.map((t) => api.list(t, "true"))).then(
      (lists) => {
        if (live) setRefs(Object.fromEntries(config.refs.map((t, i) => [t, lists[i]])));
      },
      (e: unknown) => {
        if (live) toast(describe(e), "crit");
      },
    );
    return () => {
      live = false;
    };
  }, [api, config, toast]);

  return (
    <div className={css.layout}>
      <div className={css.list}>
        <Panel
          title={config.title}
          actions={
            <RoleGate allow={["admin"]} roles={roles}>
              <Button
                variant="primary"
                onClick={() => {
                  go(`${config.path}/new`);
                }}
              >
                {`New ${config.singular}`}
              </Button>
            </RoleGate>
          }
        >
          <div className={css.filters}>
            <Select
              id="filter"
              label="Show"
              value={filter}
              options={FILTERS}
              onChange={setFilter}
            />
            <TextField id="search" label="Search" value={q} onChange={setQ} />
          </div>
          <Table
            caption={config.title}
            rows={rows ?? []}
            loading={rows === null}
            rowKey={(r) => r.id}
            selectedKey={id}
            onRowSelect={(r) => {
              go(`${config.path}/${r.id}`);
            }}
            empty={
              <EmptyState
                title={`No ${config.title.toLowerCase()} yet`}
                body={filter === "true" ? "Nothing active here." : "Nothing matches this filter."}
              />
            }
            columns={[
              ...config.columns.map((c) => ({
                key: c.key,
                header: c.header,
                render: (r: Rec) => c.render(r, refs),
              })),
              {
                key: "status",
                header: "Status",
                render: (r: Rec) => (
                  <StatusPill tone={r.active ? "ok" : "warn"}>
                    {r.active ? "Active" : "Inactive"}
                  </StatusPill>
                ),
              },
            ]}
          />
        </Panel>
      </div>
      {id && (
        <RecordPanel
          key={id}
          config={config}
          id={id}
          api={api}
          roles={roles}
          refs={refs}
          onChanged={reloadList}
        />
      )}
    </div>
  );
}

type RecordPanelProps = {
  config: MasterConfig;
  id: string;
  api: MasterApi;
  roles: Role[];
  refs: Refs;
  onChanged: () => void;
};

function RecordPanel({ config, id, api, roles, refs, onChanged }: RecordPanelProps) {
  const isNew = id === "new";
  const type = config.path;
  const toast = useToast();
  const [rec, setRec] = useState<Rec | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => {
    setTick((t) => t + 1);
    onChanged();
  }, [onChanged]);
  const fail = useFail(reload);

  useEffect(() => {
    if (isNew) return;
    let live = true;
    Promise.all([api.get(type, id), api.history(type, id)]).then(
      ([r, h]) => {
        if (!live) return;
        setRec(r);
        setHistory(h);
      },
      (e: unknown) => {
        if (live) toast(describe(e), "crit");
      },
    );
    return () => {
      live = false;
    };
  }, [api, type, id, isNew, tick, toast]);

  const toggle = (on: boolean) => {
    if (!rec) return;
    api.setActive(type, rec.id, rec.version, on).then(() => {
      toast(on ? "Reactivated" : "Deactivated", "ok");
      reload();
    }, fail);
  };

  const ctx = rec && { rec, refs, api, roles, onFail: fail, reload };
  return (
    <>
      <DetailPanel
        title={isNew ? `New ${config.singular}` : String(rec?.name ?? "Loading…")}
        open
        onClose={() => {
          go(type);
        }}
      >
        {isNew || rec ? (
          <div className={css.stack}>
            {rec && (
              <div>
                <StatusPill tone={rec.active ? "ok" : "warn"}>
                  {rec.active ? "Active" : "Inactive"}
                </StatusPill>
              </div>
            )}
            <EditForm
              key={rec ? `${rec.id}:${String(rec.version)}` : "new"}
              name="Details"
              fields={config.fields}
              initial={initialValues(config.fields, rec ?? undefined)}
              refs={refs}
              roles={roles}
              submitLabel={rec ? "Save" : "Create"}
              onFail={fail}
              onSubmit={async (body) => {
                if (rec) {
                  await api.update(type, rec.id, rec.version, body);
                  toast("Saved", "ok");
                  reload();
                } else {
                  const created = await api.create(type, body);
                  toast("Created", "ok");
                  onChanged();
                  go(`${type}/${created.id}`);
                }
              }}
            />
            {rec && (
              <div>
                <RoleGate allow={["admin"]} roles={roles}>
                  {rec.active ? (
                    <InlineConfirm
                      label="Deactivate"
                      confirmLabel="Confirm deactivate"
                      tone="crit"
                      onConfirm={() => {
                        toggle(false);
                      }}
                    />
                  ) : (
                    <Button
                      variant="secondary"
                      onClick={() => {
                        toggle(true);
                      }}
                    >
                      Reactivate
                    </Button>
                  )}
                </RoleGate>
              </div>
            )}
            {ctx && config.aside?.(ctx)}
            {rec && (
              <Panel title="History">
                <HistoryList entries={history} />
              </Panel>
            )}
          </div>
        ) : (
          <p role="status">Loading…</p>
        )}
      </DetailPanel>
      {ctx && config.below && <div className={css.below}>{config.below(ctx)}</div>}
    </>
  );
}
