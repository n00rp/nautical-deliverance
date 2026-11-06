import { createRequest, toHistory, type RawHistory, type TokenSource } from "./http";
import type { StatusPillProps } from "./ui/StatusPill/StatusPill";
import type { Role } from "./ui/RoleGate/RoleGate";

/** Engine status values mapped, in this one place, to the StatusPill labels (B0-D5). */
export const STATUS_LABEL = {
  draft: "Draft",
  rfq_sent: "RFQ sent",
  offers_received: "Offers received",
  winner_selected: "Winner selected",
  nominated: "Nominated",
  cancelled: "Cancelled",
} as const satisfies Record<string, Extract<StatusPillProps, { status: string }>["status"]>;

export type InquiryStatus = keyof typeof STATUS_LABEL;

export type ListParams = {
  /** Omitted: everything but cancelled. */
  status?: InquiryStatus | "all";
  q?: string;
  mine?: boolean;
  sort?: "eta" | "reference";
};

/** A work-list row. `eta` is null on a duplicated draft that has none yet. */
export type InquiryListItem = {
  id: string;
  reference: string;
  status: InquiryStatus;
  vessel_name: string;
  port_name: string;
  port_time_zone: string;
  eta: string | null;
  buyer_name: string | null;
  /** RFQs that are not withdrawn, and how many of those have been sent; null for the Operator. */
  rfq_total: number | null;
  rfq_sent: number | null;
  eta_warning: boolean;
};

/** Quantity and density are decimal strings, never numbers (D-074). */
type LineBody = {
  product_id: string;
  quantity: string;
  unit: "mt" | "m3";
  density?: string | null;
  spec_notes?: string | null;
  iso_spec_version_id: string;
};

export type InquiryBody = {
  vessel_id: string;
  legal_entity_id?: string | null;
  voyage?: string | null;
  operator_id?: string | null;
  buyer_id?: string | null;
  requester_id?: string | null;
  port_id: string;
  eta: string;
  etd: string;
  agent_name?: string | null;
  agent_email?: string | null;
  bunkering_reason_id: string;
  internal_comments?: string | null;
  lines: LineBody[];
};

type Line = {
  id: string;
  position: number;
  product_id: string;
  product_name: string;
  product_inactive: boolean;
  quantity: string;
  unit: string;
  density: string | null;
  not_in_total: boolean;
  spec_notes: string | null;
  iso_spec_version_id: string;
  iso_spec_version_name: string;
  iso_spec_version_inactive: boolean;
};

type InquiryWarning = { field: string; code: string; message: string };

/** The full inquiry as GET /inquiries/{id} returns it, display names included. */
export type Inquiry = {
  id: string;
  reference: string;
  status: InquiryStatus;
  version: number;
  vessel_id: string;
  vessel_name: string;
  vessel_inactive: boolean;
  legal_entity_id: string;
  legal_entity_name: string;
  legal_entity_inactive: boolean;
  voyage: string | null;
  operator_id: string;
  operator_name: string;
  buyer_id: string | null;
  buyer_name: string | null;
  requester_id: string;
  requester_name: string;
  port_id: string;
  port_name: string;
  port_locode: string;
  port_time_zone: string;
  port_inactive: boolean;
  eta: string | null;
  etd: string | null;
  agent_name: string | null;
  agent_email: string | null;
  bunkering_reason_id: string;
  bunkering_reason_name: string;
  bunkering_reason_inactive: boolean;
  internal_comments: string | null;
  cancel_reason: string | null;
  rfq_deadline: string | null;
  /** Null for the Operator, like rfq_deadline: who was contacted stays hidden. */
  rfq_total: number | null;
  rfq_sent: number | null;
  created_at: string;
  created_by: string;
  updated_at: string;
  lines: Line[];
  warnings: InquiryWarning[];
};

export type DirectoryUser = { id: string; name: string; email: string; roles: Role[] };

/** The statuses in which the engine accepts new RFQs. */
export const SUPPLIER_STATES: InquiryStatus[] = ["draft", "rfq_sent", "offers_received"];

/** Typed client for /api/v1/inquiries and /api/v1/users. */
export function createInquiryApi(auth: TokenSource) {
  const call = createRequest(auth);
  const path = (id: string, action = "") => `inquiries/${encodeURIComponent(id)}${action}`;
  const post = (id: string, action: string, body: object) =>
    call<Inquiry>("POST", path(id, action), body);

  return {
    listInquiries: (params: ListParams) => {
      const query = new URLSearchParams();
      if (params.status) query.set("status", params.status);
      if (params.q) query.set("q", params.q);
      if (params.mine) query.set("mine", "true");
      if (params.sort) query.set("sort", params.sort);
      const qs = query.toString();
      return call<InquiryListItem[]>("GET", qs ? `inquiries?${qs}` : "inquiries");
    },
    getInquiry: (id: string) => call<Inquiry>("GET", path(id)),
    createInquiry: (body: Partial<InquiryBody>) => call<Inquiry>("POST", "inquiries", body),
    patchInquiry: (id: string, version: number, body: Partial<InquiryBody>) =>
      call<Inquiry>("PATCH", path(id), { ...body, version }),
    takeInquiry: (id: string, version: number) => post(id, "/take", { version }),
    cancelInquiry: (id: string, version: number, reason: string) =>
      post(id, "/cancel", { version, reason }),
    duplicateInquiry: (id: string, version: number) => post(id, "/duplicate", { version }),
    inquiryHistory: async (id: string) =>
      toHistory(await call<RawHistory[]>("GET", path(id, "/history"))),
    listUsers: (role?: Role) => call<DirectoryUser[]>("GET", role ? `users?role=${role}` : "users"),
  };
}

export type InquiryApi = ReturnType<typeof createInquiryApi>;
