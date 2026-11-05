import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import type { Role } from "../ui/RoleGate/RoleGate";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { configFor } from "./configs";
import { MasterDataPage } from "./MasterDataPage";
import { fakeApi, rec } from "./testSupport";

const port = (id: string, locode: string, name: string, time_zone: string) =>
  rec(id, { locode, name, country: locode.slice(0, 2), time_zone });

function createApi() {
  const api = fakeApi(
    {
      counterparties: [
        rec("cp1", { name: "Alpha Fuels", type: "physical_supplier", notes: null }),
        rec("cp2", { name: "Baltic Trading", type: "trader", notes: null }),
        rec("cp3", { name: "Cape Supply", type: "both", notes: null }),
      ],
      ports: [
        port("p1", "NLRTM", "Rotterdam", "Europe/Amsterdam"),
        port("p2", "SGSIN", "Singapore", "Asia/Singapore"),
        port("p3", "GIGIB", "Gibraltar", "Europe/Gibraltar"),
      ],
      products: [
        rec("pr1", { name: "VLSFO 0.5%", default_unit: "mt" }),
        rec("pr2", { name: "DMA 0.1%", default_unit: "mt" }),
        rec("pr3", { name: "HSFO 3.5%", default_unit: "mt" }),
      ],
    },
    {
      "counterparties/cp1/coverage": [
        { port_id: "p1", product_id: "pr1" },
        { port_id: "p1", product_id: "pr2" },
        { port_id: "p2", product_id: "pr1" },
      ],
    },
    [
      rec("k1", {
        name: "Ann Example",
        email: "ann@alpha.example",
        phone: "+31 10 000 0000",
        is_primary: true,
      }),
    ],
  );
  void api.update("counterparties", "cp1", 1, { notes: "Preferred supplier" });
  return api;
}

function Page({ roles }: { roles: Role[] }) {
  const [api] = useState(createApi);
  return (
    <ToastProvider>
      <MasterDataPage config={configFor("counterparties")} api={api} roles={roles} />
      <ToastHost />
    </ToastProvider>
  );
}

const meta = {
  title: "Admin/Counterparties",
  parameters: { layout: "fullscreen" },
  beforeEach: () => {
    window.location.hash = "#/admin/counterparties/cp1";
  },
} satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

export const AsAdmin: Story = { render: () => <Page roles={["admin"]} /> };
export const AsViewer: Story = { render: () => <Page roles={["viewer"]} /> };
