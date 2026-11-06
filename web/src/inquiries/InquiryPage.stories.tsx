import type { Meta, StoryObj } from "@storybook/react-vite";
import type { Role } from "../ui/RoleGate/RoleGate";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { InquiryPage } from "./InquiryPage";
import { inquiry, inquiryApi, master } from "./pageSupport";

const [first] = inquiry().lines;
if (!first) throw new Error("fixture has no line");
/** Two lines: a not-approved fuel on the first, an m3 line without density on the second. */
const draft = inquiry({
  voyage: "V-042",
  internal_comments: "Prefer a barge delivery.",
  lines: [
    first,
    {
      ...first,
      id: "l2",
      position: 2,
      product_id: "pr3",
      product_name: "LNG",
      unit: "m3",
      not_in_total: true,
    },
  ],
  warnings: [
    {
      field: "lines[0].product_id",
      code: "not_approved_fuel",
      message: "Not approved for this vessel",
    },
  ],
});

function Page({ rec, roles }: { rec: typeof draft; roles: Role[] }) {
  return (
    <ToastProvider>
      <InquiryPage id={rec.id} api={inquiryApi(rec)} master={master} roles={roles} />
      <ToastHost />
    </ToastProvider>
  );
}

const meta = {
  title: "Inquiries/InquiryPage",
  parameters: { layout: "fullscreen" },
} satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

export const Draft: Story = { render: () => <Page rec={draft} roles={["bunker_buyer"]} /> };
export const Locked: Story = {
  render: () => <Page rec={{ ...draft, status: "rfq_sent" }} roles={["bunker_buyer"]} />,
};
export const AsOperator: Story = { render: () => <Page rec={draft} roles={["operator"]} /> };

/** A winner is selected: the buyer can create the nomination. */
export const WinnerSelected: Story = {
  render: () => (
    <Page
      rec={inquiry({ status: "winner_selected", winner_counterparty_name: "Beta Marine" })}
      roles={["bunker_buyer"]}
    />
  ),
};
