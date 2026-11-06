import { useState } from "react";
import { useBusy } from "../ui/useBusy";
import { useLoaded } from "../admin/useLoaded";
import { useReload } from "../admin/useReload";
import type { DecisionReason, InquiryApi } from "../inquiryApi";
import { formatDecimal, formatUsd, parseDecimal } from "../money";
import {
  COST_KEYS,
  COST_LABEL,
  REASON_LABEL,
  type ComparisonRow,
  type OfferApi,
} from "../offerApi";
import { Button } from "../ui/Button/Button";
import { formatInstant } from "../ui/DateTimeField/format";
import { DetailPanel } from "../ui/DetailPanel/DetailPanel";
import { EmptyState } from "../ui/EmptyState/EmptyState";
import { InlineConfirm } from "../ui/InlineConfirm/InlineConfirm";
import { LockedNote } from "../ui/LockedNote/LockedNote";
import { Panel } from "../ui/Panel/Panel";
import { access } from "../ui/RoleGate/access";
import type { Role } from "../ui/RoleGate/RoleGate";
import { StatusPill } from "../ui/StatusPill/StatusPill";
import { Table } from "../ui/Table/Table";
import { useToast } from "../ui/Toast/Toast";
import rfqs from "../rfqs/RfqLog.module.css";
import page from "../rfqs/SupplierSelection.module.css";
import { InquiryTitle } from "../inquiries/InquiryTitle";
import css from "./Comparison.module.css";
import { DecisionForm } from "./DecisionForm";

export type ComparisonProps = {
  inquiryId: string;
  api: Pick<InquiryApi, "getInquiry"> & Pick<OfferApi, "getComparison" | "selectWinner">;
  roles: Role[];
};

/** The statuses in which the engine accepts a (new) winner. */
const SELECTABLE = ["offers_received", "winner_selected"];

const RFQ_TONE = { sent: "ok", declined: "warn", withdrawn: "crit", draft: "info" } as const;
const RFQ_LABEL = { sent: "Sent", declined: "Declined", withdrawn: "Withdrawn", draft: "Draft" };
const tone = (s: string) => RFQ_TONE[s as keyof typeof RFQ_TONE];
const label = (s: string) => RFQ_LABEL[s as keyof typeof RFQ_LABEL];

/** "Partial 1 of 2" counts the inquiry lines that are in the total. */
const coverage = (r: ComparisonRow) =>
  r.complete
    ? "Complete"
    : `Partial ${String(r.lines.filter((l) => l.in_total).length)} of ${String(r.lines.length)}`;

/** Why a row cannot be selected; null when it can. */
const blocked = (r: ComparisonRow) =>
  r.expired ? "Offer has expired" : r.rfq_status === "declined" ? "RFQ was declined" : null;

/** `102.000 mt × USD 845.500 = USD 86,241.00`, or why the line is not in the total. */
function worked(l: ComparisonRow["lines"][number]): string {
  if (l.in_total && l.qty_mt && l.price_per_mt && l.line_cost) {
    const price = formatDecimal(parseDecimal(l.price_per_mt, 3), 3);
    return `${l.qty_mt} mt × USD ${price} = ${formatUsd(l.line_cost)}`;
  }
  return l.price_per_mt ? "not in total: needs a density" : "not in total: no price";
}

type Body = { reason?: DecisionReason; note?: string };

/** S6: compare the offers of an inquiry and select the winner (B4-R12). */
export function Comparison({ inquiryId, api, roles }: ComparisonProps) {
  const toast = useToast();
  const { allowed, canWrite } = access(roles);
  const [openId, setOpenId] = useState<string | null>(null);
  const [deciding, setDeciding] = useState(false);
  const { pending, guarded } = useBusy();
  const { tick, reload, fail } = useReload();
  const { data, failed } = useLoaded(allowed, async () => {
    const [inquiry, cmp] = await Promise.all([
      api.getInquiry(inquiryId),
      api.getComparison(inquiryId),
    ]);
    return { inquiry, cmp };
  }, [api, inquiryId, tick]);

  if (!allowed) return <LockedNote what="offer comparison" />;
  if (failed) {
    return <EmptyState title="Could not load the offers" body="Reload the page to try again." />;
  }
  if (!data) return <p role="status">Loading…</p>;

  const { inquiry, cmp } = data;
  const zone = inquiry.port_time_zone;
  const open = cmp.rows.find((r) => r.offer_id === openId) ?? null;
  const winner = cmp.rows.find((r) => r.offer_id === cmp.decision?.winner_offer_id);
  const canSelect = canWrite && SELECTABLE.includes(inquiry.status);

  /** One selection at a time; a stale version (409) reloads through `fail`. */
  const select = (row: ComparisonRow, body: Body) =>
    guarded(async () => {
      await api.selectWinner(inquiry.id, inquiry.version, { offer_id: row.offer_id, ...body });
      toast("Winner selected", "ok");
      setDeciding(false);
      reload();
    });

  const actions = (r: ComparisonRow) => {
    if (r.selected) return null;
    const why = blocked(r);
    if (why) {
      return (
        <Button variant="secondary" disabled title={why}>
          Select winner
        </Button>
      );
    }
    if (r.lowest) {
      return (
        <InlineConfirm
          label="Select winner"
          confirmLabel="Confirm winner"
          disabled={pending}
          onConfirm={() => {
            select(r, {}).catch(fail);
          }}
        />
      );
    }
    return (
      <Button
        variant="secondary"
        disabled={pending}
        onClick={() => {
          setOpenId(r.offer_id);
          setDeciding(true);
        }}
      >
        Select winner
      </Button>
    );
  };

  return (
    <div className={page.page}>
      <InquiryTitle
        heading={`${inquiry.reference} — Offers`}
        status={inquiry.status}
        inquiryId={inquiryId}
      />
      {cmp.decision && (
        <Panel title="Decision">
          <p className={css.decision}>
            <strong>{winner?.counterparty_name ?? "Selected offer"}</strong>
            {` at ${formatUsd(cmp.decision.decided_total)}, selected by ${cmp.decision.decided_by_name} on ${formatInstant(cmp.decision.decided_at)}`}
          </p>
          <p className={css.sub}>
            {cmp.decision.reason
              ? `Reason: ${REASON_LABEL[cmp.decision.reason]}`
              : "Selected as the lowest offer"}
            {cmp.decision.note ? `. ${cmp.decision.note}` : ""}
          </p>
        </Panel>
      )}
      <div className={rfqs.layout}>
        <div className={rfqs.main}>
          <Table
            caption="Offers"
            rows={cmp.rows}
            rowKey={(r) => r.offer_id}
            selectedKey={openId ?? undefined}
            highlight={(r) => r.lowest}
            onRowSelect={(r) => {
              setOpenId(r.offer_id);
              setDeciding(false);
            }}
            empty="No offers yet"
            columns={[
              {
                key: "cp",
                header: "Counterparty",
                render: (r) => (
                  <>
                    <span className={css.name}>{r.counterparty_name}</span>
                    {r.lowest && <StatusPill tone="ok">Lowest</StatusPill>}
                    {r.physical_supplier && <span className={css.sub}>{r.physical_supplier}</span>}
                  </>
                ),
              },
              {
                key: "cover",
                header: "Coverage",
                render: (r) =>
                  r.complete ? coverage(r) : <StatusPill tone="warn">{coverage(r)}</StatusPill>,
              },
              { key: "total", header: "Total", align: "end", render: (r) => formatUsd(r.total) },
              {
                key: "delta",
                header: "Δ to lowest",
                align: "end",
                render: (r) =>
                  r.delta_to_lowest === null || r.lowest
                    ? "—"
                    : `${r.delta_to_lowest.startsWith("-") ? "" : "+"}${formatUsd(r.delta_to_lowest)}`,
              },
              {
                key: "valid",
                header: "Valid until",
                render: (r) => (
                  <>
                    <span>{formatInstant(r.valid_until, zone)}</span>
                    {r.expired && <StatusPill tone="crit">Expired</StatusPill>}
                    {!r.expired && r.expiring_soon && (
                      <StatusPill tone="warn">Expires in less than 24 h</StatusPill>
                    )}
                  </>
                ),
              },
              {
                key: "delivery",
                header: "Delivery window",
                render: (r) =>
                  r.delivery_from && r.delivery_to
                    ? `${formatInstant(r.delivery_from, zone)} to ${formatInstant(r.delivery_to, zone)}`
                    : "—",
              },
              {
                key: "status",
                header: "Status",
                render: (r) => (
                  <span className={css.pills}>
                    <StatusPill tone={tone(r.rfq_status)}>{label(r.rfq_status)}</StatusPill>
                    {r.selected && <StatusPill tone="accent">Selected</StatusPill>}
                  </span>
                ),
              },
              ...(canSelect ? [{ key: "act", header: "Action", render: actions }] : []),
            ]}
          />
        </div>
        <DetailPanel
          title={open ? `Offer from ${open.counterparty_name}` : ""}
          open={open !== null}
          onClose={() => {
            setOpenId(null);
            setDeciding(false);
          }}
        >
          {open && (
            <div className={css.detail}>
              <ul className={css.calc} aria-label="Calculation">
                {open.lines.map((l) => (
                  <li key={l.inquiry_line_id}>
                    <span>{l.product}</span>
                    <span className={css.mono}>{worked(l)}</span>
                  </li>
                ))}
                {COST_KEYS.filter((k) => open[k] !== "0.00").map((k) => (
                  <li key={k}>
                    <span>{COST_LABEL[k]}</span>
                    <span className={css.mono}>{formatUsd(open[k])}</span>
                  </li>
                ))}
                <li className={css.total}>
                  <span>Total</span>
                  <span className={css.mono}>{formatUsd(open.total)}</span>
                </li>
              </ul>
              {open.payment_terms && (
                <p className={css.sub}>{`Payment terms: ${open.payment_terms}`}</p>
              )}
              {open.supplier_comment && <p className={css.sub}>{open.supplier_comment}</p>}
              {deciding && canSelect && (
                <DecisionForm
                  key={open.offer_id}
                  onFail={fail}
                  onCancel={() => {
                    setDeciding(false);
                  }}
                  onSubmit={(body) => select(open, body)}
                />
              )}
            </div>
          )}
        </DetailPanel>
      </div>
    </div>
  );
}
