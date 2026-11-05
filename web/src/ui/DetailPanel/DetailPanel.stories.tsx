import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import { Table } from "../Table/Table";
import { DetailPanel } from "./DetailPanel";

type Row = { id: string; name: string };
const rows: Row[] = [
  { id: "1", name: "Aegean Marine Fuels" },
  { id: "2", name: "Baltic Bunkers" },
  { id: "3", name: "Supercalifragilisticexpialidocious-Marine-Fuels-International-Limited-Group" },
];

function Compare() {
  const [open, setOpen] = useState<Row | null>(rows[2] ?? null);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "16px", alignItems: "flex-start" }}>
      <div style={{ flex: "1 1 24rem", minWidth: 0 }}>
        <Table
          caption="Offers"
          columns={[{ key: "n", header: "Supplier", render: (r: Row) => r.name }]}
          rows={rows}
          rowKey={(r) => r.id}
          selectedKey={open?.id}
          onRowSelect={(r) => setOpen(r)}
        />
      </div>
      <DetailPanel title={open?.name ?? ""} open={open !== null} onClose={() => setOpen(null)}>
        Fixed costs and per-product prices for the selected offer.
      </DetailPanel>
    </div>
  );
}

const meta = {
  title: "UI/DetailPanel",
  component: DetailPanel,
  args: { title: "Offer", open: true, onClose: () => undefined, children: "Details" },
} satisfies Meta<typeof DetailPanel>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Open: Story = {};
export const BesideTable: Story = { render: () => <Compare /> };
