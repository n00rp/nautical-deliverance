import { useState } from "react";
import { ApiError } from "../api";
import { useBusy } from "../ui/useBusy";
import { useLoaded } from "../admin/useLoaded";
import { useReload } from "../admin/useReload";
import { InquiryTitle } from "../inquiries/InquiryTitle";
import type { InquiryApi, InquiryStatus } from "../inquiryApi";
import type { NominationApi } from "../nominationApi";
import type { RfqApi, Suggestions } from "../rfqApi";
import rfqs from "../rfqs/RfqLog.module.css";
import { RfqPreview } from "../rfqs/RfqPreview";
import page from "../rfqs/SupplierSelection.module.css";
import { Button } from "../ui/Button/Button";
import { formatInstant } from "../ui/DateTimeField/format";
import { LockedNote } from "../ui/LockedNote/LockedNote";
import { Panel } from "../ui/Panel/Panel";
import { DetailPanel } from "../ui/DetailPanel/DetailPanel";
import { InlineConfirm } from "../ui/InlineConfirm/InlineConfirm";
import { EmptyState } from "../ui/EmptyState/EmptyState";
import { access } from "../ui/RoleGate/access";
import type { Role } from "../ui/RoleGate/RoleGate";
import { Select } from "../ui/Select/Select";
import { StatusPill } from "../ui/StatusPill/StatusPill";
import { Table } from "../ui/Table/Table";
import { useToast } from "../ui/Toast/Toast";

export type NominationProps = {
  inquiryId: string;
  api: Pick<InquiryApi, "getInquiry"> &
    Pick<RfqApi, "getSuggestions"> &
    Pick<
      NominationApi,
      | "listNominations"
      | "createNomination"
      | "getNominationPreview"
      | "patchNomination"
      | "markNominationSent"
      | "withdrawNomination"
    >;
  roles: Role[];
};

/** The statuses in which the engine accepts a nomination draft. */
const NOMINATABLE: InquiryStatus[] = ["winner_selected", "nominated"];

type Contact = Suggestions["covers_all"][number]["contacts"][number];

/** What the engine's 409 reason means for the buyer, with the right next step; null if unknown. */
function conflictText(e: unknown): string | null {
  if (
    e instanceof ApiError &&
    e.issues.some((i) => i.message.startsWith("Offer validity has expired"))
  ) {
    return "The winning offer's validity has expired. Record the extended validity on the offer, then send the nomination.";
  }
  const reason = e instanceof ApiError && e.status === 409 ? e.detail : null;
  if (reason?.startsWith("Winning offer changed")) {
    return "The winner changed since this draft was made. Withdraw the draft and create a new one.";
  }
  if (reason?.startsWith("Nomination total differs")) {
    return "The nomination total differs from the decision. Check the winning offer or select the winner again; a new draft would show the same total.";
  }
  if (reason === "Inquiry is cancelled") {
    return "The inquiry is cancelled, so nothing can be sent. Withdraw the draft.";
  }
  return reason?.startsWith("Inquiry is ")
    ? `${reason}: this nomination cannot be sent now.`
    : null;
}

/** The winner's contacts by counterparty id; [] when it is not listed (inactive), null on failure. */
const contactsOf = (groups: Suggestions, counterpartyId: string | null): Contact[] =>
  Object.values(groups)
    .flat()
    .filter((s) => s.counterparty_id === counterpartyId)
    .flatMap((s) => s.contacts);

/** S7: the nomination draft to the winner, its mail hand-off, and every sent version (B5-R11). */
export function Nomination({ inquiryId, api, roles }: NominationProps) {
  const toast = useToast();
  const { allowed, canWrite } = access(roles);
  const [openId, setOpenId] = useState<string | null>(null);
  const { pending, guarded } = useBusy();
  const { tick, reload, fail } = useReload();
  const { data, failed } = useLoaded(allowed, async () => {
    const [inquiry, noms] = await Promise.all([
      api.getInquiry(inquiryId),
      api.listNominations(inquiryId),
    ]);
    const drafting = canWrite && noms.some((n) => n.status === "draft");
    const contacts: Contact[] | null = drafting
      ? await api.getSuggestions(inquiryId).then(
          (g) => contactsOf(g, inquiry.winner_counterparty_id),
          () => null,
        )
      : [];
    return { inquiry, noms, contacts };
  }, [api, inquiryId, tick]);

  if (!allowed) return <LockedNote what="the nomination" />;
  if (failed) {
    return (
      <EmptyState title="Could not load the nomination" body="Reload the page to try again." />
    );
  }
  if (!data) return <p role="status">Loading…</p>;

  const { inquiry, noms, contacts } = data;
  const zone = inquiry.port_time_zone;
  const draft = noms.find((n) => n.status === "draft");
  const sent = noms.filter((n) => n.status === "sent");
  const open = sent.find((n) => n.id === openId) ?? null;
  const amending = inquiry.status === "nominated";

  /** One change at a time; a 409 with a known reason says what to do, then reloads. */
  const run = (call: () => Promise<unknown>, message: string) => {
    guarded(async () => {
      await call();
      toast(message, "ok");
      reload();
    }).catch((e: unknown) => {
      const text = conflictText(e);
      if (text) {
        toast(text, "warn");
        reload();
      } else fail(e);
    });
  };

  return (
    <div className={page.page}>
      <InquiryTitle
        heading={`${inquiry.reference} — Nomination`}
        status={inquiry.status}
        inquiryId={inquiryId}
      />
      {inquiry.winner_counterparty_name && (
        <p>{`Selected supplier: ${inquiry.winner_counterparty_name}`}</p>
      )}
      {canWrite && !draft && NOMINATABLE.includes(inquiry.status) && (
        <div>
          <Button
            variant="primary"
            disabled={pending}
            onClick={() => {
              run(() => api.createNomination(inquiryId), "Draft created");
            }}
          >
            {amending ? "Amend nomination" : "Create nomination"}
          </Button>
        </div>
      )}
      {draft && (
        <Panel title={sent.length ? "Amendment draft" : "Draft"}>
          <div className={rfqs.preview}>
            {canWrite &&
              (contacts?.length ? (
                <Select
                  id="nomination-contact"
                  label="Contact"
                  value={draft.contact_id}
                  options={contacts.map((c) => ({ value: c.id, label: `${c.name} (${c.email})` }))}
                  disabled={pending}
                  onChange={(id) => {
                    run(() => api.patchNomination(draft.id, draft.version, id), "Contact saved");
                  }}
                />
              ) : (
                <p role={contacts ? undefined : "alert"}>
                  {`Contact: ${draft.contact_name} (${draft.email}). `}
                  {contacts
                    ? "The supplier is inactive or has no active contact, so it cannot be changed."
                    : "Could not load the supplier's contacts; reload the page to change it."}
                </p>
              ))}
            <RfqPreview item={draft} load={api.getNominationPreview} />
            {canWrite && (
              <div className={rfqs.actions}>
                <InlineConfirm
                  label="Mark sent"
                  confirmLabel="Confirm sent"
                  disabled={pending}
                  onConfirm={() => {
                    run(() => api.markNominationSent(draft.id, draft.version), "Marked sent");
                  }}
                />
                <InlineConfirm
                  label="Withdraw draft"
                  confirmLabel="Confirm withdraw"
                  tone="crit"
                  disabled={pending}
                  onConfirm={() => {
                    run(() => api.withdrawNomination(draft.id, draft.version), "Draft withdrawn");
                  }}
                />
              </div>
            )}
          </div>
        </Panel>
      )}
      <div className={rfqs.layout}>
        <div className={rfqs.main}>
          <Table
            caption="Sent versions"
            rows={sent}
            rowKey={(n) => n.id}
            selectedKey={openId ?? undefined}
            onRowSelect={(n) => {
              setOpenId(n.id);
            }}
            empty="No nomination sent yet"
            columns={[
              { key: "version", header: "Version", render: (n) => `v${String(n.sequence)}` },
              { key: "sent", header: "Sent", render: (n) => formatInstant(n.sent_at ?? "", zone) },
              { key: "to", header: "To", render: (n) => `${n.contact_name} (${n.email})` },
              {
                key: "changed",
                header: "Changed",
                render: (n) =>
                  n.changed_since_sent && <StatusPill tone="warn">Changed since sent</StatusPill>,
              },
            ]}
          />
        </div>
        <DetailPanel
          title={open ? `Version ${String(open.sequence)} as sent` : ""}
          open={open !== null}
          onClose={() => {
            setOpenId(null);
          }}
        >
          {open && <RfqPreview key={open.id} item={open} load={api.getNominationPreview} />}
        </DetailPanel>
      </div>
    </div>
  );
}
