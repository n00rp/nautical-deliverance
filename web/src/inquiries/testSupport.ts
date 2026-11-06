// Sample work-list rows, shared by the WorkList tests and story.
import type { InquiryListItem } from "../inquiryApi";

export const item = (id: string, fields: Partial<InquiryListItem> = {}): InquiryListItem => ({
  id,
  reference: `INQ-2611-${id.padStart(3, "0")}`,
  status: "draft",
  vessel_name: "Test Vessel",
  port_name: "Rotterdam",
  port_time_zone: "Europe/Amsterdam",
  eta: "2026-11-12T06:00:00Z",
  buyer_name: "Bea Buyer",
  rfq_total: 0,
  rfq_sent: 0,
  offer_total: 0,
  winner_counterparty_name: null,
  eta_warning: false,
  ...fields,
});
