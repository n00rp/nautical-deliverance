import type { Meta, StoryObj } from "@storybook/react-vite";
import type { InquiryStatus } from "../inquiryApi";
import type { NominationItem } from "../nominationApi";
import type { Role } from "../ui/RoleGate/RoleGate";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { Nomination } from "./Nomination";
import { amendedNom, changedNom, draftNom, nominationApi } from "./testSupport";

const at = (roles: Role[], list: NominationItem[], status: InquiryStatus): StoryObj => ({
  render: () => (
    <ToastProvider>
      <Nomination inquiryId="i1" api={nominationApi(list, status)} roles={roles} />
      <ToastHost />
    </ToastProvider>
  ),
});

export default {
  title: "Nominations/Nomination",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

/** The first draft to the winner: preview, contact select, Mark sent and Withdraw draft. */
export const FirstDraft = at(["bunker_buyer"], [draftNom], "winner_selected");
/** An amendment draft above two sent versions; the first one is stale (ETA changed). */
export const Amendment = at(
  ["admin"],
  [{ ...draftNom, id: "n3" }, amendedNom, changedNom],
  "nominated",
);
/** Nominated without a draft: the buyer can amend. */
export const Nominated = at(["bunker_buyer"], [amendedNom, changedNom], "nominated");
export const AsViewer = at(["viewer"], [draftNom, amendedNom, changedNom], "nominated");
export const AsOperator = at(["operator"], [], "nominated");
