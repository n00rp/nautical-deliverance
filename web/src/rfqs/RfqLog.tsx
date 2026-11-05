import { useEffect, useRef, useState } from "react";
import { ApiError } from "../api";
import { describe } from "../admin/errors";
import { useReload } from "../admin/useReload";
import { STATUS_LABEL, type Inquiry, type InquiryApi } from "../inquiryApi";
import type { RfqApi, RfqItem } from "../rfqApi";
import { Button } from "../ui/Button/Button";
import { DateTimeField } from "../ui/DateTimeField/DateTimeField";
import { formatInstant } from "../ui/DateTimeField/format";
import { DetailPanel } from "../ui/DetailPanel/DetailPanel";
import { EmptyState } from "../ui/EmptyState/EmptyState";
import { InlineConfirm } from "../ui/InlineConfirm/InlineConfirm";
import { LockedNote } from "../ui/LockedNote/LockedNote";
import type { Role } from "../ui/RoleGate/RoleGate";
import { StatusPill } from "../ui/StatusPill/StatusPill";
import { Table } from "../ui/Table/Table";
import { useToast } from "../ui/Toast/Toast";
import css from "./RfqLog.module.css";
import page from "./SupplierSelection.module.css";
import { RfqPreview } from "./RfqPreview";

type Calls = Pick<RfqApi, "patchRfq" | "markSent" | "withdrawRfq" | "declineRfq">;

export type RfqLogProps = {
  inquiryId: string;
  api: Pick<InquiryApi, "getInquiry"> & Pick<RfqApi, "listRfqs" | "getPreview"> & Calls;
  roles: Role[];
};

const READERS: Role[] = ["admin", "bunker_buyer", "viewer"];
const WRITERS: Role[] = ["admin", "bunker_buyer"];

const TONE = { draft: "info", sent: "ok", declined: "warn", withdrawn: "crit" } as const;
const LABEL = {
  draft: "Draft",
  sent: "Sent",
  declined: "Declined",
  withdrawn: "Withdrawn",
} as const;

type ActionsProps = {
  rfq: RfqItem;
  api: Calls;
  timeZone: string;
  onDone: (message: string) => void;
  onFail: (e: unknown) => void;
};

const isLate = (e: unknown) =>
  e instanceof ApiError &&
  e.status === 422 &&
  e.issues.some((i) => i.field === "response_deadline");

/** Status actions of one RFQ; a passed deadline on Mark sent asks for a new one (Review Focus 5). */
function RfqActions({ rfq, api, timeZone, onDone, onFail }: ActionsProps) {
  const [pending, setPending] = useState(false);
  const [deadline, setDeadline] = useState<string | null>(null);
  const [error, setError] = useState<string | undefined>();
  const busy = useRef(false);

  const run = (call: () => Promise<unknown>, message: string) => {
    if (busy.current) return;
    busy.current = true;
    setPending(true);
    call()
      .then(() => {
        setDeadline(null);
        onDone(message);
      })
      .catch((e: unknown) => {
        if (isLate(e)) {
          setError(describe(e));
          setDeadline("");
        } else onFail(e);
      })
      .finally(() => {
        busy.current = false;
        setPending(false);
      });
  };

  return (
    <div className={css.deadline}>
      <div className={css.actions}>
        {rfq.status === "draft" && (
          <>
            <InlineConfirm
              label="Mark sent"
              confirmLabel="Confirm sent"
              disabled={pending}
              onConfirm={() => {
                run(() => api.markSent(rfq.id, rfq.version), "Marked sent");
              }}
            />
            <InlineConfirm
              label="Withdraw"
              confirmLabel="Confirm withdraw"
              tone="crit"
              disabled={pending}
              onConfirm={() => {
                run(() => api.withdrawRfq(rfq.id, rfq.version), "Withdrawn");
              }}
            />
          </>
        )}
        {rfq.status === "sent" && (
          <InlineConfirm
            label="Mark declined"
            confirmLabel="Confirm declined"
            tone="crit"
            disabled={pending}
            onConfirm={() => {
              run(() => api.declineRfq(rfq.id, rfq.version), "Marked declined");
            }}
          />
        )}
      </div>
      {deadline !== null && (
        <>
          <DateTimeField
            id="rfq-new-deadline"
            label="New offer deadline"
            required
            valueUtc={deadline}
            timeZone={timeZone}
            error={error}
            onChange={(v) => {
              setDeadline(v);
              setError(undefined);
            }}
          />
          <div>
            <Button
              variant="primary"
              loading={pending}
              disabled={!deadline}
              onClick={() => {
                run(
                  () => api.patchRfq(rfq.id, rfq.version, { response_deadline: deadline }),
                  "Deadline saved",
                );
              }}
            >
              Save deadline
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

/** S4: the RFQs of one inquiry with the mail preview and status actions (B3-R12, B3-R13). */
export function RfqLog({ inquiryId, api, roles }: RfqLogProps) {
  const toast = useToast();
  const allowed = roles.some((r) => READERS.includes(r));
  const canWrite = roles.some((r) => WRITERS.includes(r));
  const [data, setData] = useState<{ inquiry: Inquiry; rfqs: RfqItem[] } | null>(null);
  const [failed, setFailed] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const { tick, reload, fail } = useReload();

  useEffect(() => {
    if (!allowed) return;
    let live = true;
    const load = async () => {
      try {
        const [inquiry, rfqs] = await Promise.all([
          api.getInquiry(inquiryId),
          api.listRfqs(inquiryId),
        ]);
        if (!live) return;
        setData({ inquiry, rfqs });
        setFailed(false);
      } catch (e) {
        if (!live) return;
        setFailed(true);
        toast(describe(e), "crit");
      }
    };
    void load();
    return () => {
      live = false;
    };
  }, [api, inquiryId, allowed, tick, toast]);

  if (!allowed) return <LockedNote what="the RFQ log" />;
  if (failed && !data)
    return <EmptyState title="Could not load RFQs" body="Reload the page to try again." />;
  if (!data) return <p role="status">Loading…</p>;

  const { inquiry, rfqs } = data;
  const zone = inquiry.port_time_zone;
  const when = (iso: string | null) => (iso ? formatInstant(iso, zone) : "—");
  const open = rfqs.find((r) => r.id === openId) ?? null;

  return (
    <div className={page.page}>
      <div className={page.title}>
        <h2 className={page.heading}>{`${inquiry.reference} — RFQs`}</h2>
        <StatusPill status={STATUS_LABEL[inquiry.status]} />
        <div className={css.links}>
          <a className={page.back} href={`#/inquiries/${inquiryId}`}>
            Back to inquiry
          </a>
          {canWrite && (
            <a className={page.back} href={`#/inquiries/${inquiryId}/suppliers`}>
              Select suppliers
            </a>
          )}
        </div>
      </div>
      <div className={css.layout}>
        <div className={css.main}>
          <Table
            caption="RFQs"
            rows={rfqs}
            rowKey={(r) => r.id}
            selectedKey={openId ?? undefined}
            onRowSelect={(r) => {
              setOpenId(r.id);
            }}
            empty="No RFQs yet"
            columns={[
              { key: "to", header: "Recipient", render: (r) => r.counterparty_name },
              { key: "contact", header: "Contact", render: (r) => r.contact_name },
              { key: "email", header: "Address", render: (r) => r.email },
              { key: "gen", header: "Generated", render: (r) => when(r.generated_at) },
              { key: "sent", header: "Sent", render: (r) => when(r.sent_at) },
              {
                key: "status",
                header: "Status",
                render: (r) => (
                  <span className={css.nowrap}>
                    <StatusPill tone={TONE[r.status]}>{LABEL[r.status]}</StatusPill>
                  </span>
                ),
              },
              { key: "deadline", header: "Deadline", render: (r) => when(r.response_deadline) },
              {
                key: "offer",
                header: "Offer received",
                render: (r) => (r.offer_received ? "Yes" : "—"),
              },
              {
                key: "changed",
                header: "Changed",
                render: (r) =>
                  r.changed_since_sent && <StatusPill tone="warn">Changed since sent</StatusPill>,
              },
            ]}
          />
        </div>
        <DetailPanel
          title={open ? `RFQ to ${open.counterparty_name}` : ""}
          open={open !== null}
          onClose={() => {
            setOpenId(null);
          }}
        >
          {open && (
            <>
              <RfqPreview key={open.id} rfq={open} api={api} />
              {canWrite && (
                <RfqActions
                  key={open.id}
                  rfq={open}
                  api={api}
                  timeZone={zone}
                  onFail={fail}
                  onDone={(message) => {
                    toast(message, "ok");
                    reload();
                  }}
                />
              )}
            </>
          )}
        </DetailPanel>
      </div>
    </div>
  );
}
