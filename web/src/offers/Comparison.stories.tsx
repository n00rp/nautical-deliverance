import type { Meta, StoryObj } from "@storybook/react-vite";
import type { InquiryStatus } from "../inquiryApi";
import type { Comparison as Data } from "../offerApi";
import type { Role } from "../ui/RoleGate/RoleGate";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { Comparison } from "./Comparison";
import {
  compareApi,
  completeOnly,
  decided,
  offersInquiry,
  partialAndExpired,
  tie,
} from "./comparisonSupport";

const story = (data: Data, roles: Role[], status: InquiryStatus = "offers_received"): StoryObj => ({
  render: () => (
    <ToastProvider>
      <Comparison inquiryId="i1" api={compareApi(data, offersInquiry({ status }))} roles={roles} />
      <ToastHost />
    </ToastProvider>
  ),
});

export default {
  title: "Offers/Comparison",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

/** Three complete offers; the lowest is highlighted. */
export const CompleteOnly = story(completeOnly, ["bunker_buyer"]);
/** Two offers at the same total are both the lowest. */
export const Tie = story(tie, ["bunker_buyer"]);
/** A partial offer, one expiring soon, an expired and a declined one that cannot be selected. */
export const PartialAndExpired = story(partialAndExpired, ["bunker_buyer"]);
/** A winner is selected (not the lowest), with the rationale shown. */
export const Decided = story(decided, ["admin"], "winner_selected");
export const AsViewer = story(decided, ["viewer"], "winner_selected");
export const AsOperator = story(completeOnly, ["operator"]);
