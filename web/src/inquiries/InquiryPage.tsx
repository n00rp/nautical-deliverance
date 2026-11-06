import { useCallback, useEffect, useState } from "react";
import { describe, useFail } from "../admin/errors";
import { goInquiry } from "../admin/routes";
import {
  STATUS_LABEL,
  SUPPLIER_STATES,
  type Inquiry,
  type InquiryApi,
  type InquiryBody,
} from "../inquiryApi";
import type { MasterApi } from "../masterApi";
import type { NominationApi } from "../nominationApi";
import { Button } from "../ui/Button/Button";
import { EmptyState } from "../ui/EmptyState/EmptyState";
import { HistoryList, type HistoryEntry } from "../ui/HistoryList/HistoryList";
import { Panel } from "../ui/Panel/Panel";
import { access } from "../ui/RoleGate/access";
import { RoleGate, type Role } from "../ui/RoleGate/RoleGate";
import { StatusPill } from "../ui/StatusPill/StatusPill";
import { useToast } from "../ui/Toast/Toast";
import { useBusy } from "../ui/useBusy";
import { CancelAction } from "./CancelAction";
import admin from "../admin/Admin.module.css";
import css from "./Inquiry.module.css";
import { InquiryForm, type Refs } from "./InquiryForm";

export type InquiryPageProps = {
  /** An inquiry id, or "new". */
  id: string;
  api: InquiryApi & Pick<NominationApi, "createNomination" | "listNominations">;
  master: Pick<MasterApi, "list">;
  roles: Role[];
};

async function loadRefs(
  api: Pick<InquiryApi, "listUsers">,
  master: Pick<MasterApi, "list">,
): Promise<Refs> {
  const list = (t: Parameters<MasterApi["list"]>[0]) => master.list(t, "true");
  const [vessels, ports, legalEntities, products, isos, reasons, users] = await Promise.all([
    list("vessels"),
    list("ports"),
    list("legal-entities"),
    list("products"),
    list("iso-spec-versions"),
    list("bunkering-reasons"),
    api.listUsers(),
  ]);
  // The engine accepts an admin as operator or buyer too (inquiries.py _check_refs).
  const has = (...roles: Role[]) => users.filter((u) => u.roles.some((r) => roles.includes(r)));
  return {
    vessels,
    ports,
    legalEntities,
    products,
    isos,
    reasons,
    users,
    operators: has("operator", "admin"),
    buyers: has("bunker_buyer", "admin"),
  };
}

/** Writers can always open the log; readers only once there is an RFQ to read. */
const showLog = (rec: Inquiry, roles: Role[]) =>
  access(roles).canWrite || (access(roles).allowed && (rec.rfq_total ?? 0) > 0);

/** The comparison opens once offers can exist, for everyone who may read them. */
const showOffers = (rec: Inquiry, roles: Role[]) =>
  access(roles).allowed && ["offers_received", "winner_selected", "nominated"].includes(rec.status);

/** The nomination screen is for readers once a winner is selected. */
const showNomination = (rec: Inquiry, roles: Role[]) =>
  access(roles).allowed && ["winner_selected", "nominated"].includes(rec.status);

/** Create, edit and act on one inquiry (B2-R13). */
export function InquiryPage({ id, api, master, roles }: InquiryPageProps) {
  const isNew = id === "new";
  const toast = useToast();
  const [refs, setRefs] = useState<Refs | null>(null);
  const [rec, setRec] = useState<Inquiry | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [failed, setFailed] = useState(false);
  const { pending, guarded } = useBusy();
  const [tick, setTick] = useState(0);
  // Bumps with every load, so the form restarts from the server state (drafts survive failures).
  const [epoch, setEpoch] = useState(0);
  const reload = useCallback(() => {
    setTick((t) => t + 1);
  }, []);
  const fail = useFail(reload);
  const loadFailed = useCallback(
    (e: unknown) => {
      setFailed(true);
      toast(describe(e), "crit");
    },
    [toast],
  );

  useEffect(() => {
    let live = true;
    loadRefs(api, master).then(
      (r) => {
        if (live) setRefs(r);
      },
      (e: unknown) => {
        if (live) loadFailed(e);
      },
    );
    return () => {
      live = false;
    };
  }, [api, master, loadFailed]);

  useEffect(() => {
    if (isNew) return;
    let live = true;
    Promise.all([api.getInquiry(id), api.inquiryHistory(id)]).then(
      ([r, h]) => {
        if (!live) return;
        setRec(r);
        setHistory(h);
        setEpoch((n) => n + 1);
      },
      (e: unknown) => {
        if (live) loadFailed(e);
      },
    );
    return () => {
      live = false;
    };
  }, [api, id, isNew, tick, loadFailed]);

  if (failed) {
    return <EmptyState title="Could not load this inquiry" body="Reload the page to try again." />;
  }
  if (!refs || (!isNew && !rec)) return <p role="status">Loading…</p>;

  const act = (run: (r: Inquiry) => Promise<void>) => {
    if (rec) guarded(() => run(rec)).catch(fail);
  };
  const done = (message: string) => {
    toast(message, "ok");
    reload();
  };
  const names = new Map(refs.users.map((u) => [u.id, u.name]));

  return (
    <div className={css.page}>
      <div className={css.title}>
        <h2 className={css.heading}>{rec ? rec.reference : "New inquiry"}</h2>
        {rec && <StatusPill status={STATUS_LABEL[rec.status]} />}
        {rec && showLog(rec, roles) && (
          <a className={css.link} href={`#/inquiries/${rec.id}/rfqs`}>
            RFQs
          </a>
        )}
        {rec && showNomination(rec, roles) && (
          <a className={css.link} href={`#/inquiries/${rec.id}/nomination`}>
            Nomination
          </a>
        )}
        {rec && showOffers(rec, roles) && (
          <a className={css.link} href={`#/inquiries/${rec.id}/offers`}>
            Compare offers
          </a>
        )}
      </div>
      {rec?.winner_counterparty_name && (
        <p className={css.info}>
          {`${rec.status === "nominated" ? "Nominated" : "Selected supplier"}: ${rec.winner_counterparty_name}`}
        </p>
      )}
      {rec?.cancel_reason && <p className={css.info}>{`Cancelled: ${rec.cancel_reason}`}</p>}
      <InquiryForm
        key={`${id}:${String(epoch)}`}
        rec={rec}
        refs={refs}
        roles={roles}
        onFail={fail}
        onCreate={async (body: InquiryBody) => {
          const created = await api.createInquiry(body);
          toast("Created", "ok");
          goInquiry(created.id);
        }}
        onPatch={async (body) => {
          if (!rec) return;
          await api.patchInquiry(rec.id, rec.version, body);
          done("Saved");
        }}
      />
      {rec && (
        <div className={css.side}>
          <RoleGate allow={["admin", "bunker_buyer"]} roles={roles}>
            <Panel title="Actions">
              <div className={css.stack}>
                <div className={admin.actions}>
                  {rec.buyer_id === null && rec.status !== "cancelled" && (
                    <Button
                      variant="primary"
                      disabled={pending}
                      onClick={() => {
                        act(async (r) => {
                          await api.takeInquiry(r.id, r.version);
                          done("Taken");
                        });
                      }}
                    >
                      Take
                    </Button>
                  )}
                  {SUPPLIER_STATES.includes(rec.status) && (
                    <Button
                      variant={rec.buyer_id === null ? "secondary" : "primary"}
                      onClick={() => {
                        goInquiry(`${rec.id}/suppliers`);
                      }}
                    >
                      Select suppliers
                    </Button>
                  )}
                  {showNomination(rec, roles) && (
                    <Button
                      variant="primary"
                      disabled={pending}
                      onClick={() => {
                        act(async (r) => {
                          // One draft at a time: an existing one is opened, not created again.
                          const noms = await api.listNominations(r.id);
                          if (!noms.some((n) => n.status === "draft")) {
                            await api.createNomination(r.id);
                          }
                          goInquiry(`${r.id}/nomination`);
                        });
                      }}
                    >
                      {rec.status === "nominated" ? "Amend nomination" : "Create nomination"}
                    </Button>
                  )}
                  <Button
                    variant="secondary"
                    disabled={pending}
                    onClick={() => {
                      act(async (r) => {
                        const copy = await api.duplicateInquiry(r.id, r.version);
                        toast("Duplicated as a new Draft", "ok");
                        goInquiry(copy.id);
                      });
                    }}
                  >
                    Duplicate
                  </Button>
                </div>
                {rec.status !== "cancelled" && (
                  <CancelAction
                    disabled={pending}
                    onCancel={(reason) => {
                      act(async (r) => {
                        await api.cancelInquiry(r.id, r.version, reason);
                        done("Cancelled");
                      });
                    }}
                  />
                )}
              </div>
            </Panel>
          </RoleGate>
          <Panel title="History">
            <HistoryList
              entries={history.map((e) => ({ ...e, actor: names.get(e.actor) ?? e.actor }))}
            />
          </Panel>
        </div>
      )}
    </div>
  );
}
