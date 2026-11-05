// Sample reference data and inquiries, shared by the InquiryPage tests and stories.
import type { DirectoryUser, Inquiry, InquiryApi } from "../inquiryApi";
import type { MasterApi, MasterType, Rec } from "../masterApi";

const r = (id: string, fields: Record<string, string | number | null>): Rec => ({
  id,
  active: true,
  version: 1,
  ...fields,
});

const DATA: Partial<Record<MasterType, Rec[]>> = {
  vessels: [
    r("v1", {
      name: "Northern Star",
      imo: "9000001",
      vessel_type: "Product tanker",
      dwt: 50000,
      legal_entity_id: "le1",
      default_operator: "op1",
    }),
    r("v2", {
      name: "Harbour Light",
      imo: "9000002",
      vessel_type: "Bulk carrier",
      dwt: 80000,
      legal_entity_id: "le2",
      default_operator: "op2",
    }),
  ],
  ports: [
    r("p1", { name: "Rotterdam", time_zone: "Europe/Amsterdam" }),
    r("p2", { name: "Singapore", time_zone: "Asia/Singapore" }),
  ],
  "legal-entities": [r("le1", { name: "Alpha Marine" }), r("le2", { name: "Beta Shipping" })],
  products: [
    r("pr1", { name: "VLSFO 0.5%", default_unit: "mt" }),
    r("pr2", { name: "MGO 0.1%", default_unit: "mt" }),
    r("pr3", { name: "LNG", default_unit: "m3" }),
  ],
  "iso-spec-versions": [r("iso1", { name: "ISO 8217:2024" })],
  "bunkering-reasons": [r("br1", { name: "Regular bunkering" })],
};

export const master: Pick<MasterApi, "list"> = {
  list: (type) => Promise.resolve((DATA[type] ?? []).map((x) => ({ ...x }))),
};

const OPERATORS: DirectoryUser[] = [
  { id: "op1", name: "Olga Operator", email: "olga@demo.example", roles: ["operator"] },
  { id: "op2", name: "Oskar Operator", email: "oskar@demo.example", roles: ["operator"] },
];
const BUYERS: DirectoryUser[] = [
  { id: "b1", name: "Bea Buyer", email: "bea@demo.example", roles: ["bunker_buyer"] },
];
const ADMINS: DirectoryUser[] = [
  { id: "ad1", name: "Ada Admin", email: "ada@demo.example", roles: ["admin"] },
];

/** A Draft with one VLSFO line; override any field. */
export const inquiry = (fields: Partial<Inquiry> = {}): Inquiry => ({
  id: "i1",
  reference: "INQ-2611-001",
  status: "draft",
  version: 1,
  vessel_id: "v1",
  vessel_name: "Northern Star",
  vessel_inactive: false,
  legal_entity_id: "le1",
  legal_entity_name: "Alpha Marine",
  legal_entity_inactive: false,
  voyage: null,
  operator_id: "op1",
  operator_name: "Olga Operator",
  buyer_id: "b1",
  buyer_name: "Bea Buyer",
  requester_id: "op1",
  requester_name: "Olga Operator",
  port_id: "p1",
  port_name: "Rotterdam",
  port_locode: "NLRTM",
  port_time_zone: "Europe/Amsterdam",
  port_inactive: false,
  eta: "2026-11-12T06:00:00Z",
  etd: "2026-11-13T06:00:00Z",
  agent_name: null,
  agent_email: null,
  bunkering_reason_id: "br1",
  bunkering_reason_name: "Regular bunkering",
  bunkering_reason_inactive: false,
  internal_comments: null,
  cancel_reason: null,
  created_at: "2026-11-05T09:00:00Z",
  created_by: "op1",
  updated_at: "2026-11-05T09:00:00Z",
  lines: [
    {
      id: "l1",
      position: 1,
      product_id: "pr1",
      product_name: "VLSFO 0.5%",
      product_inactive: false,
      quantity: "500",
      unit: "mt",
      density: null,
      not_in_total: false,
      spec_notes: null,
      iso_spec_version_id: "iso1",
      iso_spec_version_name: "ISO 8217:2024",
      iso_spec_version_inactive: false,
    },
  ],
  warnings: [],
  ...fields,
});

/** Inquiry client that serves one inquiry and answers every action with it. */
export function inquiryApi(current: Inquiry = inquiry()): InquiryApi {
  const same = () => Promise.resolve(current);
  return {
    listInquiries: () => Promise.resolve([]),
    getInquiry: same,
    createInquiry: same,
    patchInquiry: same,
    takeInquiry: same,
    cancelInquiry: same,
    duplicateInquiry: same,
    inquiryHistory: () =>
      Promise.resolve([
        {
          id: "h1",
          actor: "op1",
          at: "2026-11-05T09:00:00Z",
          action: "create",
          changes: [{ field: "status", before: null, after: "draft" }],
        },
      ]),
    // Like the engine: no role means everyone; a role filter matches the user's own roles.
    listUsers: (role) =>
      Promise.resolve(
        [...OPERATORS, ...BUYERS, ...ADMINS].filter((u) => !role || u.roles.includes(role)),
      ),
  };
}
