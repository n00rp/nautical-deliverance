import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { describe } from "../admin/errors";
import { goInquiry } from "../admin/routes";
import { useReload } from "../admin/useReload";
import { useSave } from "../admin/useSave";
import type { Inquiry, InquiryApi } from "../inquiryApi";
import { evaluateOffer, formatUsd } from "../money";
import {
  COST_KEYS,
  type DeliveryMethod,
  type Offer,
  type OfferApi,
  type OfferBody,
} from "../offerApi";
import type { RfqApi, RfqItem } from "../rfqApi";
import { Button } from "../ui/Button/Button";
import { DateTimeField } from "../ui/DateTimeField/DateTimeField";
import { EmptyState } from "../ui/EmptyState/EmptyState";
import { FormSummary } from "../ui/FormSummary/FormSummary";
import { LockedNote } from "../ui/LockedNote/LockedNote";
import { NumberField } from "../ui/NumberField/NumberField";
import { Panel } from "../ui/Panel/Panel";
import type { Role } from "../ui/RoleGate/RoleGate";
import { Select } from "../ui/Select/Select";
import { StatusPill } from "../ui/StatusPill/StatusPill";
import { TextField } from "../ui/TextField/TextField";
import { useToast } from "../ui/Toast/Toast";
import page from "../rfqs/SupplierSelection.module.css";
import css from "./OfferEntry.module.css";

export type OfferEntryProps = {
  inquiryId: string;
  rfqId: string;
  api: Pick<InquiryApi, "getInquiry"> &
    Pick<RfqApi, "listRfqs"> &
    Pick<OfferApi, "getOffer" | "createOffer" | "patchOffer">;
  roles: Role[];
};

const NEGATIVE = "Must not be negative";
const WRITERS: Role[] = ["admin", "bunker_buyer"];

const METHODS: { value: DeliveryMethod; label: string }[] = [
  { value: "barge", label: "Barge" },
  { value: "truck", label: "Truck" },
  { value: "pipeline", label: "Pipeline" },
  { value: "ex_wharf", label: "Ex-wharf" },
];

const COST_LABEL = {
  barging_cost: "Barging",
  port_call_cost: "Port call",
  agent_cost: "Agent",
  surveyor_cost: "Surveyor",
  other_cost: "Other",
} as const;

// Form field ids; the engine's 422 field names map onto them (see `target`).
const VALID = "offer-valid-until";
const FROM = "offer-delivery-from";
const TO = "offer-delivery-to";
const METHOD = "offer-method";
const TERMS = "offer-terms";
const SUPPLIER = "offer-supplier";
const COMMENT = "offer-comment";
const SIMPLE: Record<string, string> = {
  valid_until: VALID,
  delivery_from: FROM,
  delivery_to: TO,
  delivery_method: METHOD,
  payment_terms: TERMS,
  physical_supplier: SUPPLIER,
  supplier_comment: COMMENT,
  ...Object.fromEntries(COST_KEYS.map((k) => [k, `cost-${k}`])),
};

/** B4-D6: an offer may state a density only for an m3 line the inquiry gave none. */
const asksDensity = (l: Inquiry["lines"][number]) => l.unit === "m3" && l.density === null;

/** The values of a form, keyed by field id, from the offer being edited (if any). */
function initial(inquiry: Inquiry, offer: Offer | undefined): Record<string, string> {
  if (!offer) return {};
  const values: Record<string, string> = {
    [VALID]: offer.valid_until,
    [FROM]: offer.delivery_from ?? "",
    [TO]: offer.delivery_to ?? "",
    [METHOD]: offer.delivery_method ?? "",
    [TERMS]: offer.payment_terms ?? "",
    [SUPPLIER]: offer.physical_supplier ?? "",
    [COMMENT]: offer.supplier_comment ?? "",
  };
  for (const k of COST_KEYS) values[`cost-${k}`] = offer[k];
  for (const l of inquiry.lines) {
    const mine = offer.lines.find((x) => x.inquiry_line_id === l.id);
    values[`price-${l.id}`] = mine?.price_per_mt ?? "";
    values[`density-${l.id}`] = mine?.density ?? "";
  }
  return values;
}

type FormProps = {
  inquiry: Inquiry;
  rfq: RfqItem;
  offer: Offer | undefined;
  api: Pick<OfferApi, "createOffer" | "patchOffer">;
  onFail: (e: unknown) => void;
};

function OfferForm({ inquiry, rfq, offer, api, onFail }: FormProps) {
  const toast = useToast();
  const [v, setV] = useState(() => initial(inquiry, offer));
  // The inquiry lines that carried a price when last saved: a 422 names them by position.
  const [sent, setSent] = useState<string[]>([]);
  const { form, issues, clear, forbidden, busy, submit } = useSave(onFail);
  const inflight = useRef(false);

  const target = (name: string) => {
    const m = /^lines\[(\d+)\]\.(price_per_mt|density)$/.exec(name);
    const line = sent.find((_, i) => String(i) === m?.[1]);
    if (m && line) return `${m[2] === "density" ? "density" : "price"}-${line}`;
    return SIMPLE[name] ?? "offer-form";
  };
  // A negative amount is a field error; it counts as blank so the total stays visible.
  const negative = (id: string) => v[id]?.startsWith("-") === true;
  const num = (id: string) => (negative(id) ? "" : v[id]);
  const negatives = Object.keys(v).filter(negative);
  const err = (id: string) =>
    negative(id) ? NEGATIVE : issues.find((i) => target(i.field) === id)?.message;
  const field = (id: string) => ({
    id,
    value: v[id] ?? "",
    error: err(id),
    onChange: (x: string) => {
      setV((p) => ({ ...p, [id]: x }));
      clear((f) => target(f) === id);
    },
  });

  const calc = useMemo(() => {
    try {
      return evaluateOffer({
        lines: inquiry.lines.map((l) => ({
          line_id: l.id,
          unit: l.unit === "m3" ? "m3" : "mt",
          quantity: l.quantity,
          inquiry_density: l.density,
          price_per_mt: num(`price-${l.id}`) || null,
          offer_density: asksDensity(l) ? num(`density-${l.id}`) || null : null,
        })),
        fixed: COST_KEYS.map((k) => num(`cost-${k}`) || "0"),
      });
    } catch (e) {
      return e instanceof Error ? e.message : "Cannot compute the total";
    }
  }, [inquiry.lines, v]);

  const save = submit(async () => {
    if (inflight.current || negatives.length > 0) return;
    inflight.current = true;
    const text = (id: string) => v[id]?.trim() || null;
    const priced = inquiry.lines.filter((l) => v[`price-${l.id}`]);
    setSent(priced.map((l) => l.id));
    const body: OfferBody = {
      valid_until: v[VALID] ?? "",
      payment_terms: text(TERMS),
      delivery_from: v[FROM] || null,
      delivery_to: v[TO] || null,
      delivery_method: (v[METHOD] || null) as DeliveryMethod | null,
      physical_supplier: text(SUPPLIER),
      supplier_comment: text(COMMENT),
      ...Object.fromEntries(COST_KEYS.map((k) => [k, v[`cost-${k}`] || "0.00"])),
      lines: priced.map((l) => ({
        inquiry_line_id: l.id,
        price_per_mt: v[`price-${l.id}`] ?? "",
        ...(asksDensity(l) && v[`density-${l.id}`] ? { density: v[`density-${l.id}`] } : {}),
      })),
    };
    try {
      if (offer) await api.patchOffer(offer.id, offer.version, body);
      else await api.createOffer(rfq.id, body);
      toast("Offer saved", "ok");
      goInquiry(`${inquiry.id}/rfqs`);
    } finally {
      inflight.current = false;
    }
  });

  const results = typeof calc === "string" ? [] : calc.lines;
  const costText = (id: string, unit: string): ReactNode => {
    const r = results.find((x) => x.line_id === id);
    if (r?.line_cost) return `${r.qty_mt ?? ""} mt = ${formatUsd(r.line_cost)}`;
    return unit === "m3" && r?.qty_mt === null ? "Needs a density" : "Not in total";
  };

  return (
    <form
      ref={form}
      id="offer-form"
      aria-label="Offer"
      noValidate
      className={page.form}
      onSubmit={(e) => void save(e)}
    >
      <FormSummary
        errors={[
          ...negatives.map((fieldId) => ({ fieldId, message: NEGATIVE })),
          ...issues.map((i) => ({ fieldId: target(i.field), message: i.message })),
        ]}
      />
      <Panel title="Prices">
        {inquiry.lines.map((l) => (
          <div key={l.id} className={css.line}>
            <div className={css.grid}>
              <NumberField
                {...field(`price-${l.id}`)}
                label={`${l.product_name} — ${l.quantity} ${l.unit}`}
                decimals={3}
                dotIsDecimal
                hint="USD per mt. Leave blank for no offer. Use '.' as decimal point"
              />
              {asksDensity(l) && (
                <NumberField
                  {...field(`density-${l.id}`)}
                  label={`Density for ${l.product_name}`}
                  decimals={1}
                  hint="kg/m3, 600 to 1100"
                />
              )}
            </div>
            <p className={css.cost}>{costText(l.id, l.unit)}</p>
          </div>
        ))}
      </Panel>
      <Panel title="Total">
        {typeof calc === "string" ? (
          <p role="alert">{calc}</p>
        ) : (
          <>
            <p className={css.total} aria-live="polite">
              {formatUsd(calc.total)}
            </p>
            {!calc.complete && (
              <p className={css.partial}>
                <StatusPill tone="warn">Partial</StatusPill>
                Lines without a price or density are not in the total.
              </p>
            )}
          </>
        )}
      </Panel>
      <Panel title="Fixed costs (USD)">
        <div className={css.grid}>
          {COST_KEYS.map((k) => (
            <NumberField key={k} {...field(`cost-${k}`)} label={COST_LABEL[k]} decimals={2} />
          ))}
        </div>
      </Panel>
      <Panel title="Terms">
        <div className={css.grid}>
          <DateTimeField
            {...field(VALID)}
            valueUtc={v[VALID] ?? ""}
            label="Valid until"
            required
            timeZone={inquiry.port_time_zone}
          />
          <DateTimeField
            {...field(FROM)}
            valueUtc={v[FROM] ?? ""}
            label="Delivery from"
            timeZone={inquiry.port_time_zone}
          />
          <DateTimeField
            {...field(TO)}
            valueUtc={v[TO] ?? ""}
            label="Delivery to"
            timeZone={inquiry.port_time_zone}
          />
          <Select {...field(METHOD)} label="Delivery method" options={METHODS} emptyLabel="None" />
          <TextField {...field(TERMS)} label="Payment terms" />
          <TextField {...field(SUPPLIER)} label="Physical supplier" />
          <TextField {...field(COMMENT)} label="Comment" />
        </div>
      </Panel>
      {forbidden ? (
        <LockedNote what="saving offers" />
      ) : (
        <div>
          <Button type="submit" variant="primary" loading={busy} disabled={!v[VALID]}>
            Save offer
          </Button>
        </div>
      )}
    </form>
  );
}

/** S5: enter or edit the offer of one sent RFQ with live exact totals (B4-R12). */
export function OfferEntry({ inquiryId, rfqId, api, roles }: OfferEntryProps) {
  const toast = useToast();
  const allowed = roles.some((r) => WRITERS.includes(r));
  const [data, setData] = useState<{
    inquiry: Inquiry;
    rfqs: RfqItem[];
    offer: Offer | undefined;
  } | null>(null);
  const { tick, fail } = useReload();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!allowed) return;
    let live = true;
    const load = async () => {
      try {
        const [inquiry, rfqs] = await Promise.all([
          api.getInquiry(inquiryId),
          api.listRfqs(inquiryId),
        ]);
        const offerId = rfqs.find((r) => r.id === rfqId)?.offer_id;
        const offer = offerId ? await api.getOffer(offerId) : undefined;
        if (live) setData({ inquiry, rfqs, offer });
      } catch (e) {
        if (live) {
          setFailed(true);
          toast(describe(e), "crit");
        }
      }
    };
    void load();
    return () => {
      live = false;
    };
  }, [allowed, api, inquiryId, rfqId, tick, toast]);

  if (!allowed) return <LockedNote what="offer entry" />;
  if (failed) {
    return <EmptyState title="Could not load the offer" body="Reload the page to try again." />;
  }
  if (!data) return <p role="status">Loading…</p>;

  const { inquiry, offer } = data;
  const rfq = data.rfqs.find((r) => r.id === rfqId);
  if (!rfq || (!offer && rfq.status !== "sent")) {
    return (
      <EmptyState
        title="No offer can be entered"
        body="Offers are entered for RFQs that have been sent."
      />
    );
  }

  return (
    <div className={page.page}>
      <div className={page.title}>
        <h2 className={page.heading}>
          {`${inquiry.reference} — ${offer ? "Edit" : "Enter"} offer from ${rfq.counterparty_name}`}
        </h2>
        <a className={page.back} href={`#/inquiries/${inquiryId}/rfqs`}>
          Back to RFQs
        </a>
      </div>
      <OfferForm key={tick} inquiry={inquiry} rfq={rfq} offer={offer} api={api} onFail={fail} />
    </div>
  );
}
