import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import { StatusPill } from "../StatusPill/StatusPill";
import { Table, type TableProps } from "./Table";

type Offer = {
  id: string;
  supplier: string;
  port: string;
  total: number;
  status: "Draft" | "Nominated";
};

const suppliers = [
  "Aegean Marine Fuels",
  "Baltic Bunkers",
  "Cape Supply",
  "Delta Oil",
  "Eastern Fuel",
];
const offers: Offer[] = Array.from({ length: 15 }, (_, i) => ({
  id: `o${i}`,
  supplier: `${suppliers[i % suppliers.length] ?? ""} ${i + 1}`,
  port: ["Gibraltar", "Rotterdam", "Singapore"][i % 3] ?? "",
  total: 412_300.5 + i * 1_234.25,
  status: i % 4 === 0 ? "Nominated" : "Draft",
}));

const columns: TableProps<Offer>["columns"] = [
  { key: "supplier", header: "Supplier", render: (r) => r.supplier, sortValue: (r) => r.supplier },
  { key: "port", header: "Port", render: (r) => r.port, sortValue: (r) => r.port },
  { key: "status", header: "Status", render: (r) => <StatusPill status={r.status} /> },
  {
    key: "total",
    header: "Total (USD)",
    align: "end",
    render: (r) => r.total.toFixed(2),
    sortValue: (r) => r.total,
  },
];

function Selectable(props: TableProps<Offer>) {
  const [selected, setSelected] = useState<string | undefined>(props.selectedKey);
  return <Table {...props} selectedKey={selected} onRowSelect={(r) => setSelected(r.id)} />;
}

const meta = {
  title: "UI/Table",
  component: Table<Offer>,
  args: { columns, rows: offers, rowKey: (r: Offer) => r.id, caption: "Offers" },
} satisfies Meta<typeof Table<Offer>>;
export default meta;
type Story = StoryObj<typeof meta>;

export const OfferTable: Story = {
  render: (args) => <Selectable {...args} selectedKey="o2" />,
};
export const LongName: Story = {
  args: {
    rows: [
      {
        id: "long",
        supplier:
          "Supercalifragilisticexpialidocious".repeat(3) + "-Marine-Fuels-International-Limited",
        port: "Rotterdam",
        total: 1234567.89,
        status: "Draft",
      },
      ...offers.slice(0, 2),
    ],
  },
};
export const Empty: Story = { args: { rows: [], empty: "No offers received yet" } };
export const Loading: Story = { args: { loading: true } };
