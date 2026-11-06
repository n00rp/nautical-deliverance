import { useLoaded } from "../admin/useLoaded";
import type { AttentionItem, AttentionKind, DashboardApi, MonthFigures } from "../dashboardApi";
import { STATUS_LABEL, type InquiryStatus } from "../inquiryApi";
import { formatMt, formatUsd } from "../money";
import { formatInstant } from "../ui/DateTimeField/format";
import { EmptyState } from "../ui/EmptyState/EmptyState";
import { Panel } from "../ui/Panel/Panel";
import { StatusPill } from "../ui/StatusPill/StatusPill";
import { Table } from "../ui/Table/Table";
import css from "./Dashboard.module.css";

export type DashboardProps = { api: Pick<DashboardApi, "getDashboard"> };

const KINDS: Record<AttentionKind, { label: string; tone: "warn" | "crit" }> = {
  rfq_deadline: { label: "RFQ deadline", tone: "crit" },
  offer_validity: { label: "Offer validity", tone: "warn" },
  eta_unnominated: { label: "ETA, not nominated", tone: "crit" },
  rfq_drafts_unsent: { label: "RFQ drafts unsent", tone: "warn" },
};

const COLUMNS = [
  {
    key: "kind",
    header: "What",
    render: (i: AttentionItem) => (
      <StatusPill tone={KINDS[i.kind].tone}>{KINDS[i.kind].label}</StatusPill>
    ),
  },
  {
    key: "inquiry",
    header: "Inquiry",
    render: (i: AttentionItem) => <a href={`#/inquiries/${i.inquiry_id}`}>{i.reference}</a>,
  },
  {
    key: "vessel",
    header: "Vessel",
    render: (i: AttentionItem) => `${i.vessel_name}, ${i.port_name}`,
  },
  {
    key: "due",
    header: "Due",
    render: (i: AttentionItem) =>
      i.due_at === null ? (
        <span className={css.muted}>—</span>
      ) : (
        formatInstant(i.due_at, i.port_time_zone)
      ),
  },
  { key: "detail", header: "Detail", render: (i: AttentionItem) => i.detail ?? "" },
];

function Month({ month }: { month: MonthFigures }) {
  const excluded = month.mt_excluded_lines;
  return (
    <Panel title={`Month ${month.period}`}>
      <dl className={css.tiles}>
        <div className={css.tile}>
          <dt>Nominated spend</dt>
          <dd>{formatUsd(month.nominated_spend)}</dd>
        </div>
        <div className={css.tile}>
          <dt>Nominated volume</dt>
          <dd>
            {formatMt(month.nominated_mt)} mt
            {excluded > 0 && (
              <span className={css.note}> excl. {String(excluded)} lines without density</span>
            )}
          </dd>
        </div>
        <div className={css.tile}>
          <dt>Avg offers per inquiry</dt>
          <dd>{month.avg_offers ?? "—"}</dd>
        </div>
      </dl>
    </Panel>
  );
}

/** The start page: what needs attention, inquiries per status and the month's figures (B5-R11). */
export function Dashboard({ api }: DashboardProps) {
  const { data, failed } = useLoaded(true, () => api.getDashboard(), [api]);
  if (failed) return <EmptyState title="Could not load the dashboard" body="Reload the page." />;
  if (!data) return <p role="status">Loading…</p>;
  return (
    <div className={css.stack}>
      <Panel title="Needs attention">
        <Table
          caption="Inquiries needing attention"
          rows={data.attention}
          rowKey={(i) => `${i.inquiry_id}-${i.kind}`}
          empty={
            <EmptyState title="Nothing needs attention" body="No deadlines or ETAs are close." />
          }
          columns={COLUMNS}
        />
      </Panel>
      <Panel title="Inquiries by status">
        <dl className={css.tiles}>
          {(Object.keys(STATUS_LABEL) as InquiryStatus[]).map((s) => (
            <div key={s} className={css.tile}>
              <dt>
                <StatusPill status={STATUS_LABEL[s]} />
              </dt>
              <dd>{String(data.status_counts[s])}</dd>
            </div>
          ))}
        </dl>
      </Panel>
      {data.month && <Month month={data.month} />}
    </div>
  );
}
