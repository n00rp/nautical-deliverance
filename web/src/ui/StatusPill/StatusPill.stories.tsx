import type { Meta, StoryObj } from "@storybook/react-vite";
import { StatusPill } from "./StatusPill";

function All() {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
      {(
        [
          "Draft",
          "RFQ sent",
          "Offers received",
          "Winner selected",
          "Nominated",
          "Cancelled",
        ] as const
      ).map((s) => (
        <StatusPill key={s} status={s} />
      ))}
      <StatusPill tone="warn">RFQ deadline tomorrow 10:00</StatusPill>
      <StatusPill tone="crit">ETA in 18 h, not nominated</StatusPill>
      <StatusPill tone="ok">All requested</StatusPill>
    </div>
  );
}

const meta = { title: "UI/StatusPill", component: StatusPill } satisfies Meta<typeof StatusPill>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Statuses: Story = { args: { status: "Draft" }, render: () => <All /> };
