import { createRequest, type TokenSource } from "./http";
import type { InquiryStatus } from "./inquiryApi";

export type AttentionKind =
  "rfq_deadline" | "offer_validity" | "eta_unnominated" | "rfq_drafts_unsent";

/** One thing that needs attention; `due_at` is null for unsent RFQ drafts. */
export type AttentionItem = {
  inquiry_id: string;
  reference: string;
  vessel_name: string;
  port_name: string;
  port_time_zone: string;
  kind: AttentionKind;
  due_at: string | null;
  detail: string | null;
};

/** The UTC calendar month's figures; amounts and volumes are exact decimal strings. */
export type MonthFigures = {
  period: string;
  nominated_mt: string;
  mt_excluded_lines: number;
  nominated_spend: string;
  currency: string;
  open_by_status: Record<string, number>;
  avg_offers: string | null;
};

/** `month` is null for the Operator, who also gets only ETA items. */
export type Dashboard = {
  attention: AttentionItem[];
  status_counts: Record<InquiryStatus, number>;
  month: MonthFigures | null;
};

/** Typed client for GET /api/v1/dashboard. */
export function createDashboardApi(auth: TokenSource) {
  const call = createRequest(auth);
  return { getDashboard: () => call<Dashboard>("GET", "dashboard") };
}

export type DashboardApi = ReturnType<typeof createDashboardApi>;
