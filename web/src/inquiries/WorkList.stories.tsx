import type { Meta, StoryObj } from "@storybook/react-vite";
import type { Role } from "../ui/RoleGate/RoleGate";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { item } from "./testSupport";
import { WorkList } from "./WorkList";

const rows = [
  item("1", { vessel_name: "Northern Star", eta_warning: true, status: "rfq_sent" }),
  item("2", { vessel_name: "Harbour Light", port_name: "Singapore", buyer_name: null }),
  item("3", {
    vessel_name: "Cape Example",
    status: "nominated",
    eta: "2026-11-20T14:30:00Z",
    rfq_total: 3,
    rfq_sent: 3,
    nomination_sent: 2,
  }),
  item("4", { vessel_name: "Blue Demo", eta: null }),
];
const api = {
  listInquiries: () => Promise.resolve(rows),
  phaseCounts: () => Promise.resolve({ list: 1, market: 2, stemmed: 1, cancelled: 0 }),
};

function Page({ roles }: { roles: Role[] }) {
  return (
    <ToastProvider>
      <WorkList api={api} roles={roles} />
      <ToastHost />
    </ToastProvider>
  );
}

const meta = { title: "Inquiries/WorkList", parameters: { layout: "fullscreen" } } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

export const AsBuyer: Story = { render: () => <Page roles={["bunker_buyer"]} /> };
export const AsViewer: Story = { render: () => <Page roles={["viewer"]} /> };
