import { createRequest, type TokenSource } from "./http";
import type { RfqPreview } from "./rfqApi";

/** One version of the inquiry's nomination, newest first in the list. */
export type NominationItem = {
  id: string;
  status: "draft" | "sent" | "withdrawn";
  /** 1, 2, … for sent versions; null while a draft or withdrawn. */
  sequence: number | null;
  contact_id: string;
  contact_name: string;
  email: string;
  sent_at: string | null;
  changed_since_sent: boolean;
  version: number;
};

/** Typed client for the nomination routes under /api/v1. */
export function createNominationApi(auth: TokenSource) {
  const call = createRequest(auth);
  const nomination = (id: string, tail = "") => `nominations/${encodeURIComponent(id)}${tail}`;
  const inquiry = (id: string) => `inquiries/${encodeURIComponent(id)}/nominations`;
  const act = (id: string, action: string, version: number) =>
    call<NominationItem>("POST", nomination(id, `/${action}`), { version });

  return {
    listNominations: (inquiryId: string) => call<NominationItem[]>("GET", inquiry(inquiryId)),
    /** Without a contact the engine uses the winner's. */
    createNomination: (inquiryId: string, contactId?: string) =>
      call<NominationItem>("POST", inquiry(inquiryId), contactId ? { contact_id: contactId } : {}),
    getNominationPreview: (id: string) => call<RfqPreview>("GET", nomination(id, "/preview")),
    patchNomination: (id: string, version: number, contactId: string) =>
      call<NominationItem>("PATCH", nomination(id), { version, contact_id: contactId }),
    markNominationSent: (id: string, version: number) => act(id, "mark-sent", version),
    withdrawNomination: (id: string, version: number) => act(id, "withdraw", version),
  };
}

export type NominationApi = ReturnType<typeof createNominationApi>;
