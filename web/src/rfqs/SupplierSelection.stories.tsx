import type { Meta, StoryObj } from "@storybook/react-vite";
import type { Role } from "../ui/RoleGate/RoleGate";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { SupplierSelection } from "./SupplierSelection";
import { rfqApi, sentRfq, supplier, suggestions, twoProducts } from "./testSupport";

const rec = { ...twoProducts(), rfq_deadline: "2026-11-10T08:00:00Z" };
const groups = {
  ...suggestions,
  covers_all: [
    supplier("Alpha"),
    supplier("Beta", { type: "trader", active_rfq_id: sentRfq.id }),
    supplier("Cobalt", { contacts: [], primary_contact_id: null }),
  ],
};
const api = rfqApi(rec, groups, [sentRfq]);

function Page({ roles }: { roles: Role[] }) {
  return (
    <ToastProvider>
      <SupplierSelection inquiryId={rec.id} api={api} roles={roles} />
      <ToastHost />
    </ToastProvider>
  );
}

const meta = {
  title: "RFQs/SupplierSelection",
  parameters: { layout: "fullscreen" },
} satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

export const AsBuyer: Story = { render: () => <Page roles={["bunker_buyer"]} /> };
export const AsOperator: Story = { render: () => <Page roles={["operator"]} /> };
