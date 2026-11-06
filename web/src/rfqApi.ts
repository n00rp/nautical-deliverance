import { createRequest, toHistory, type RawHistory, type TokenSource } from "./http";

type SuggestedContact = { id: string; name: string; email: string; is_primary: boolean };

export type Suggestion = {
  counterparty_id: string;
  name: string;
  type: string;
  contacts: SuggestedContact[];
  primary_contact_id: string | null;
  covered_product_ids: string[];
  /** Set when the counterparty already has an RFQ that is not withdrawn. */
  active_rfq_id: string | null;
};

export type Suggestions = {
  covers_all: Suggestion[];
  covers_some: Suggestion[];
  not_listed: Suggestion[];
};

type RfqStatus = "draft" | "sent" | "declined" | "withdrawn";

/** One row of the RFQ log. */
export type RfqItem = {
  id: string;
  counterparty_name: string;
  contact_name: string;
  email: string;
  generated_at: string;
  sent_at: string | null;
  status: RfqStatus;
  response_deadline: string;
  offer_received: boolean;
  offer_id: string | null;
  changed_since_sent: boolean;
  version: number;
};

export type RfqPreview = {
  to: string;
  subject: string;
  body: string;
  mailto: string;
  body_in_link: boolean;
};

export type Recipient = { counterparty_id: string; contact_id: string };

/** Typed client for the RFQ routes under /api/v1. */
export function createRfqApi(auth: TokenSource) {
  const call = createRequest(auth);
  const rfq = (id: string, action = "") => `rfqs/${encodeURIComponent(id)}${action}`;
  const inquiry = (id: string, tail: string) => `inquiries/${encodeURIComponent(id)}/${tail}`;
  const act = (id: string, action: string, version: number) =>
    call<RfqItem>("POST", rfq(id, `/${action}`), { version });

  return {
    getSuggestions: (inquiryId: string) =>
      call<Suggestions>("GET", inquiry(inquiryId, "suggestions")),
    listRfqs: (inquiryId: string) => call<RfqItem[]>("GET", inquiry(inquiryId, "rfqs")),
    createRfqs: (inquiryId: string, body: { deadline: string; recipients: Recipient[] }) =>
      call<RfqItem[]>("POST", inquiry(inquiryId, "rfqs"), body),
    getPreview: (id: string) => call<RfqPreview>("GET", rfq(id, "/preview")),
    patchRfq: (
      id: string,
      version: number,
      body: { contact_id?: string; response_deadline?: string },
    ) => call<RfqItem>("PATCH", rfq(id), { ...body, version }),
    markSent: (id: string, version: number) => act(id, "mark-sent", version),
    withdrawRfq: (id: string, version: number) => act(id, "withdraw", version),
    declineRfq: (id: string, version: number) => act(id, "decline", version),
    rfqHistory: async (id: string) =>
      toHistory(await call<RawHistory[]>("GET", rfq(id, "/history"))),
  };
}

export type RfqApi = ReturnType<typeof createRfqApi>;
