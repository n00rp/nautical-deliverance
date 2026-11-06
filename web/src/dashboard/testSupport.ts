// Sample dashboards, shared by the Dashboard tests and stories.
import type { AttentionItem, Dashboard } from "../dashboardApi";

const at = (kind: AttentionItem["kind"], n: string, f: Partial<AttentionItem> = {}) => ({
  inquiry_id: `i${n}`,
  reference: `INQ-2611-00${n}`,
  vessel_name: "Test Vessel",
  port_name: "Rotterdam",
  port_time_zone: "Europe/Amsterdam",
  kind,
  due_at: "2026-11-12T06:00:00Z",
  detail: null,
  ...f,
});

const counts: Dashboard["status_counts"] = {
  draft: 2,
  rfq_sent: 1,
  offers_received: 3,
  winner_selected: 0,
  nominated: 4,
  cancelled: 1,
};

export const full: Dashboard = {
  attention: [
    at("rfq_deadline", "1", { detail: "2 RFQ(s) without offer" }),
    at("offer_validity", "2", { detail: "Offer from Alpha Marine" }),
    at("eta_unnominated", "3"),
    at("rfq_drafts_unsent", "4", { due_at: null, detail: "1 RFQ draft(s) not sent" }),
  ],
  status_counts: counts,
  month: {
    period: "2026-11",
    nominated_mt: "1234.5",
    mt_excluded_lines: 2,
    nominated_spend: "987654.30",
    currency: "USD",
    open_by_status: { draft: 2, rfq_sent: 1, offers_received: 3, winner_selected: 0 },
    avg_offers: "2.50",
  },
};

export const empty: Dashboard = {
  attention: [],
  status_counts: {
    draft: 0,
    rfq_sent: 0,
    offers_received: 0,
    winner_selected: 0,
    nominated: 0,
    cancelled: 0,
  },
  month: {
    period: "2026-11",
    nominated_mt: "0.000",
    mt_excluded_lines: 0,
    nominated_spend: "0.00",
    currency: "USD",
    open_by_status: {},
    avg_offers: null,
  },
};

/** What the Operator gets: ETA items and counts only. */
export const operator: Dashboard = {
  attention: [at("eta_unnominated", "3")],
  status_counts: counts,
  month: null,
};
