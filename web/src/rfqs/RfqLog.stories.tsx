import type { Meta, StoryObj } from "@storybook/react-vite";
import type { Role } from "../ui/RoleGate/RoleGate";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { RfqLog } from "./RfqLog";
import { changedRfq, declinedRfq, draftRfq, logApi, sentRfq } from "./testSupport";

const api = logApi([draftRfq, sentRfq, declinedRfq, changedRfq]);

const at = (roles: Role[]): StoryObj => ({
  render: () => (
    <ToastProvider>
      <RfqLog inquiryId="i1" api={api} roles={roles} />
      <ToastHost />
    </ToastProvider>
  ),
});

export default {
  title: "RFQs/RfqLog",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

/** Draft, sent, declined and changed-since-sent rows. */
export const AsBuyer = at(["bunker_buyer"]);
export const AsViewer = at(["viewer"]);
export const AsOperator = at(["operator"]);
