import { useEffect, useRef, useState } from "react";
import type { FieldIssue } from "../api";
import { describe } from "../admin/errors";
import { useReload } from "../admin/useReload";
import { goInquiry } from "../admin/routes";
import { useSave } from "../admin/useSave";
import type { Inquiry, InquiryApi } from "../inquiryApi";
import type { RfqApi, RfqItem, Suggestion, Suggestions } from "../rfqApi";
import { Button } from "../ui/Button/Button";
import { Checkbox } from "../ui/Checkbox/Checkbox";
import { DateTimeField } from "../ui/DateTimeField/DateTimeField";
import { EmptyState } from "../ui/EmptyState/EmptyState";
import { FormSummary } from "../ui/FormSummary/FormSummary";
import { LockedNote } from "../ui/LockedNote/LockedNote";
import { Panel } from "../ui/Panel/Panel";
import type { Role } from "../ui/RoleGate/RoleGate";
import { Select } from "../ui/Select/Select";
import { Table } from "../ui/Table/Table";
import { useToast } from "../ui/Toast/Toast";
import css from "./SupplierSelection.module.css";

export type SupplierSelectionProps = {
  inquiryId: string;
  api: Pick<InquiryApi, "getInquiry"> & Pick<RfqApi, "getSuggestions" | "listRfqs" | "createRfqs">;
  roles: Role[];
};

const HOUR_MS = 3_600_000;
const WRITERS: Role[] = ["admin", "bunker_buyer"];

/** The inquiry's RFQ deadline; else ETA - 48 h when the ETA is at least 72 h away; else empty. */
function defaultDeadline(inq: Inquiry, now = Date.now()): string {
  const iso = (ms: number) => `${new Date(ms).toISOString().slice(0, 16)}:00.000Z`;
  if (inq.rfq_deadline) return iso(Date.parse(inq.rfq_deadline));
  if (inq.eta === null) return "";
  const eta = Date.parse(inq.eta);
  return eta - now >= 72 * HOUR_MS ? iso(eta - 48 * HOUR_MS) : "";
}

/** "1 RFQ draft", "2 RFQ drafts". */
const drafts = (n: number) => `${String(n)} RFQ ${n === 1 ? "draft" : "drafts"}`;
const unusable = (s: Suggestion) => s.active_rfq_id !== null || s.contacts.length === 0;
const contactLabel = (c: Suggestion["contacts"][number]) => `${c.name} (${c.email})`;

type Rows = {
  selected: Set<string>;
  contact: Record<string, string>;
  statuses: Map<string, RfqItem["status"]>;
  errors: FieldIssue[];
  order: string[];
  productNames: Map<string, string>;
  onSelect: (cp: string, on: boolean) => void;
  onContact: (cp: string, contact: string) => void;
};

const rowPrefix = (r: Rows, cp: string) => `recipients[${String(r.order.indexOf(cp))}].`;

function note(s: Suggestion, r: Rows, partial: boolean) {
  if (s.active_rfq_id !== null) return `RFQ ${r.statuses.get(s.active_rfq_id) ?? "created"}`;
  if (s.contacts.length === 0) return "No contact with an e-mail address";
  if (!partial) return "";
  const names = s.covered_product_ids.map((p) => r.productNames.get(p)).filter(Boolean);
  return `Covers: ${names.join(", ")}`;
}

type TableProps = { caption: string; rows: Suggestion[]; r: Rows; partial?: boolean };

function SupplierTable({ caption, rows, r, partial }: TableProps) {
  return (
    <Table
      caption={caption}
      rows={rows}
      rowKey={(s) => s.counterparty_id}
      columns={[
        {
          key: "select",
          header: "Select",
          render: (s) => (
            <Checkbox
              id={`select-${s.counterparty_id}`}
              label={`Select ${s.name}`}
              hideLabel
              checked={r.selected.has(s.counterparty_id)}
              disabled={unusable(s)}
              onChange={(on) => {
                r.onSelect(s.counterparty_id, on);
              }}
            />
          ),
        },
        { key: "name", header: "Supplier", render: (s) => s.name },
        { key: "type", header: "Type", render: (s) => s.type.replace(/_/g, " ") },
        {
          key: "contact",
          header: "Contact",
          render: (s) => (
            <div className={css.contact}>
              <Select
                id={`contact-${s.counterparty_id}`}
                label={`Contact for ${s.name}`}
                value={r.contact[s.counterparty_id] ?? ""}
                options={s.contacts.map((c) => ({ value: c.id, label: contactLabel(c) }))}
                disabled={unusable(s)}
                error={
                  r.errors.find((e) => e.field.startsWith(rowPrefix(r, s.counterparty_id)))?.message
                }
                onChange={(id) => {
                  r.onContact(s.counterparty_id, id);
                }}
              />
            </div>
          ),
        },
        { key: "note", header: "Note", render: (s) => note(s, r, partial === true) },
      ]}
    />
  );
}

type FormProps = {
  inquiry: Inquiry;
  suggestions: Suggestions;
  rfqs: RfqItem[];
  api: Pick<RfqApi, "createRfqs">;
  onFail: (e: unknown) => void;
};

function SelectionForm({ inquiry, suggestions, rfqs, api, onFail }: FormProps) {
  const toast = useToast();
  const { covers_all: full, covers_some: some, not_listed: other } = suggestions;
  const all = [...full, ...some, ...other];
  const [deadline, setDeadline] = useState(() => defaultDeadline(inquiry));
  const [selected, setSelected] = useState(
    () => new Set(full.filter((s) => !unusable(s)).map((s) => s.counterparty_id)),
  );
  const [contact, setContact] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      all.map((s) => [s.counterparty_id, s.primary_contact_id ?? s.contacts[0]?.id ?? ""]),
    ),
  );
  // The recipients as last submitted: a 422 names them by position.
  const [order, setOrder] = useState<string[]>([]);
  const { form, issues, clear, forbidden, busy, submit } = useSave(onFail);
  const inflight = useRef(false);

  const chosen = all.filter((s) => selected.has(s.counterparty_id));
  const rows: Rows = {
    selected,
    contact,
    order,
    errors: issues,
    statuses: new Map(rfqs.map((x) => [x.id, x.status])),
    productNames: new Map(inquiry.lines.map((l) => [l.product_id, l.product_name])),
    onSelect: (cp, on) => {
      setSelected((s) => {
        const next = new Set(s);
        if (on) next.add(cp);
        else next.delete(cp);
        return next;
      });
    },
    onContact: (cp, id) => {
      clear((f) => f.startsWith(rowPrefix(rows, cp)));
      setContact((c) => ({ ...c, [cp]: id }));
    },
  };

  const save = submit(async () => {
    if (inflight.current) return;
    inflight.current = true;
    setOrder(chosen.map((s) => s.counterparty_id));
    try {
      await api.createRfqs(inquiry.id, {
        deadline,
        recipients: chosen.map((s) => ({
          counterparty_id: s.counterparty_id,
          contact_id: contact[s.counterparty_id] ?? "",
        })),
      });
      toast(`Created ${drafts(chosen.length)}`, "ok");
      goInquiry(`${inquiry.id}/rfqs`);
    } finally {
      inflight.current = false;
    }
  });

  const summary = issues.map((i) => {
    const cp = order.find((id) => i.field.startsWith(rowPrefix(rows, id)));
    return {
      fieldId: cp ? `contact-${cp}` : i.field === "deadline" ? "rfq-deadline" : "rfq-form",
      message: i.message,
    };
  });
  const n = chosen.length;

  return (
    <form
      ref={form}
      id="rfq-form"
      aria-label="Supplier selection"
      noValidate
      className={css.form}
      onSubmit={(e) => void save(e)}
    >
      <FormSummary errors={summary} />
      <Panel title="Deadline">
        <div className={css.deadline}>
          <DateTimeField
            id="rfq-deadline"
            label="Offer deadline"
            required
            valueUtc={deadline}
            timeZone={inquiry.port_time_zone}
            error={issues.find((i) => i.field === "deadline")?.message}
            onChange={(v) => {
              setDeadline(v);
              clear((f) => f === "deadline");
            }}
          />
        </div>
      </Panel>
      <Panel title={`Covers all products (${String(full.length)})`}>
        {full.length === 0 ? (
          <EmptyState
            title="No supplier covers every product"
            body="Pick from the suppliers that cover some of them."
          />
        ) : (
          <SupplierTable caption="Suppliers covering all products" rows={full} r={rows} />
        )}
      </Panel>
      {some.length > 0 && (
        <Panel title={`Covers some products (${String(some.length)})`}>
          <SupplierTable caption="Suppliers covering some products" rows={some} r={rows} partial />
        </Panel>
      )}
      {other.length > 0 && (
        <Panel>
          <details className={css.more}>
            <summary>{`Not listed for this port (${String(other.length)})`}</summary>
            <SupplierTable caption="Suppliers not listed for this port" rows={other} r={rows} />
          </details>
        </Panel>
      )}
      {forbidden ? (
        <LockedNote what="creating RFQs" />
      ) : (
        <div>
          <Button type="submit" variant="primary" loading={busy} disabled={n === 0 || !deadline}>
            {`Create ${drafts(n)}`}
          </Button>
        </div>
      )}
    </form>
  );
}

/** S3: pick the suppliers and contacts, set the deadline, create one draft per supplier (B3-R13). */
export function SupplierSelection({ inquiryId, api, roles }: SupplierSelectionProps) {
  const toast = useToast();
  const allowed = roles.some((r) => WRITERS.includes(r));
  const [data, setData] = useState<{
    inquiry: Inquiry;
    suggestions: Suggestions;
    rfqs: RfqItem[];
  } | null>(null);
  const [failed, setFailed] = useState(false);
  const { tick, fail } = useReload();

  useEffect(() => {
    if (!allowed) return;
    let live = true;
    Promise.all([api.getInquiry(inquiryId), api.getSuggestions(inquiryId), api.listRfqs(inquiryId)])
      .then(([inquiry, suggestions, rfqs]) => {
        if (live) setData({ inquiry, suggestions, rfqs });
      })
      .catch((e: unknown) => {
        if (!live) return;
        setFailed(true);
        toast(describe(e), "crit");
      });
    return () => {
      live = false;
    };
  }, [api, inquiryId, allowed, tick, toast]);

  if (!allowed) return <LockedNote what="supplier selection" />;
  if (failed) {
    return <EmptyState title="Could not load suppliers" body="Reload the page to try again." />;
  }
  if (!data) return <p role="status">Loading…</p>;

  return (
    <div className={css.page}>
      <div className={css.title}>
        <h2 className={css.heading}>{`${data.inquiry.reference} — Select suppliers`}</h2>
        <a className={css.back} href={`#/inquiries/${inquiryId}`}>
          Back to inquiry
        </a>
      </div>
      <SelectionForm
        key={tick}
        inquiry={data.inquiry}
        suggestions={data.suggestions}
        rfqs={data.rfqs}
        api={api}
        onFail={fail}
      />
    </div>
  );
}
