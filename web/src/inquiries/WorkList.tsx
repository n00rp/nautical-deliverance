import { useEffect, useState } from "react";
import { describe } from "../admin/errors";
import { goInquiry } from "../admin/routes";
import {
  STATUS_LABEL,
  SUPPLIER_STATES,
  type InquiryApi,
  type InquiryListItem,
  type InquiryStatus,
  type ListParams,
} from "../inquiryApi";
import { Button } from "../ui/Button/Button";
import { Checkbox } from "../ui/Checkbox/Checkbox";
import { EmptyState } from "../ui/EmptyState/EmptyState";
import { formatInstant } from "../ui/DateTimeField/format";
import { Select } from "../ui/Select/Select";
import { Panel } from "../ui/Panel/Panel";
import { RoleGate, type Role } from "../ui/RoleGate/RoleGate";
import { StatusPill } from "../ui/StatusPill/StatusPill";
import { Table } from "../ui/Table/Table";
import { TextField } from "../ui/TextField/TextField";
import { useToast } from "../ui/Toast/Toast";
import css from "./WorkList.module.css";

export type WorkListProps = { api: Pick<InquiryApi, "listInquiries">; roles: Role[] };

type Filter = InquiryStatus | "open" | "all";
type Sort = NonNullable<ListParams["sort"]>;

const STATUS_OPTIONS: { value: Filter; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "all", label: "All" },
  ...(Object.entries(STATUS_LABEL) as [InquiryStatus, string][]).map(([value, label]) => ({
    value,
    label,
  })),
];
const SORT_OPTIONS: { value: Sort; label: string }[] = [
  { value: "eta", label: "ETA" },
  { value: "reference", label: "Reference" },
];
const DEBOUNCE_MS = 250;

/** What to do next; the counts are null for the Operator, who then sees the status only. */
function nextStep(r: InquiryListItem) {
  if (r.status === "cancelled") return "—";
  if (r.status === "draft" && r.buyer_name === null) return "Assign buyer";
  const { rfq_total: total, rfq_sent: sent } = r;
  if (total === null || sent === null) {
    const label = r.status === "nominated" ? "Nominated" : "Selected supplier";
    return r.winner_counterparty_name
      ? `${label}: ${r.winner_counterparty_name}`
      : STATUS_LABEL[r.status];
  }
  if (r.status === "winner_selected" || (r.status === "nominated" && r.nomination_sent)) {
    const text = r.nomination_sent
      ? `Nominated (v${String(r.nomination_sent)})`
      : "Create nomination";
    return <a href={`#/inquiries/${r.id}/nomination`}>{text}</a>;
  }
  if (r.status === "offers_received" && r.offer_total) {
    const n = r.offer_total;
    return (
      <a href={`#/inquiries/${r.id}/offers`}>{`Compare ${String(n)} offer${n === 1 ? "" : "s"}`}</a>
    );
  }
  if (r.status === "draft" && total === 0) return "Create RFQs";
  if (SUPPLIER_STATES.includes(r.status) && sent < total) {
    return (
      <a href={`#/inquiries/${r.id}/rfqs`}>{`${String(sent)} of ${String(total)} RFQs sent`}</a>
    );
  }
  return STATUS_LABEL[r.status];
}

const eta = (r: InquiryListItem) =>
  r.eta === null ? (
    <span className={css.muted}>ETA missing</span>
  ) : (
    <span className={css.eta}>
      {formatInstant(r.eta, r.port_time_zone)}
      {r.eta_warning && (
        <StatusPill tone="crit">
          {Date.parse(r.eta) < Date.now() ? "ETA passed" : "ETA in < 48 h"}, not nominated
        </StatusPill>
      )}
    </span>
  );

const COLUMNS = [
  { key: "reference", header: "Reference", render: (r: InquiryListItem) => r.reference },
  { key: "vessel", header: "Vessel", render: (r: InquiryListItem) => r.vessel_name },
  { key: "port", header: "Port", render: (r: InquiryListItem) => r.port_name },
  { key: "eta", header: "ETA", render: eta },
  {
    key: "status",
    header: "Status",
    render: (r: InquiryListItem) => <StatusPill status={STATUS_LABEL[r.status]} />,
  },
  { key: "next", header: "Next step", render: nextStep },
  {
    key: "buyer",
    header: "Buyer",
    render: (r: InquiryListItem) => r.buyer_name ?? <span className={css.muted}>Unassigned</span>,
  },
];

/** The start page: every inquiry the caller may see, filtered and sorted by the engine (B2-R12). */
export function WorkList({ api, roles }: WorkListProps) {
  const toast = useToast();
  const [filter, setFilter] = useState<Filter>("open");
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [mine, setMine] = useState(false);
  const [sort, setSort] = useState<Sort>("eta");
  const [rows, setRows] = useState<InquiryListItem[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setQ(text);
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [text]);

  useEffect(() => {
    let live = true;
    const params: ListParams = { sort };
    if (filter !== "open") params.status = filter;
    if (q) params.q = q;
    if (mine) params.mine = true;
    void (async () => {
      try {
        const loaded = await api.listInquiries(params);
        if (!live) return;
        setRows(loaded);
        setFailed(false);
      } catch (e) {
        if (!live) return;
        setRows([]);
        setFailed(true);
        toast(describe(e), "crit");
      }
    })();
    return () => {
      live = false;
    };
  }, [api, filter, q, mine, sort, toast]);

  const create = (
    <RoleGate allow={["admin", "bunker_buyer", "operator"]} roles={roles}>
      <Button
        variant="primary"
        onClick={() => {
          goInquiry("new");
        }}
      >
        New inquiry
      </Button>
    </RoleGate>
  );

  return (
    <Panel title="Inquiries" actions={create}>
      <div className={css.filters}>
        <Select
          id="status"
          label="Status"
          value={filter}
          options={STATUS_OPTIONS}
          onChange={setFilter}
        />
        <TextField id="search" label="Search" value={text} onChange={setText} />
        <Select id="sort" label="Sort" value={sort} options={SORT_OPTIONS} onChange={setSort} />
        <RoleGate allow={["admin", "bunker_buyer"]} roles={roles}>
          <Checkbox id="mine" label="Mine" checked={mine} onChange={setMine} />
        </RoleGate>
      </div>
      <Table
        caption="Inquiries"
        rows={rows ?? []}
        loading={rows === null}
        rowKey={(r) => r.id}
        onRowSelect={(r) => {
          goInquiry(r.id);
        }}
        empty={
          failed ? (
            <EmptyState
              title="Could not load inquiries"
              body="Change the filter or reload the page to try again."
            />
          ) : (
            <EmptyState title="No inquiries" body="Nothing matches this filter." />
          )
        }
        columns={COLUMNS}
      />
    </Panel>
  );
}
