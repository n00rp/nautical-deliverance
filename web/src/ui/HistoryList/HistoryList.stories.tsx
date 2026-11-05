import type { Meta, StoryObj } from "@storybook/react-vite";
import { HistoryList } from "./HistoryList";

const meta = {
  title: "UI/HistoryList",
  component: HistoryList,
  args: {
    entries: [
      { id: "1", actor: "Ann Admin", at: "2026-11-01T08:00:00Z", action: "create", changes: [] },
      {
        id: "3",
        actor: "Cid Buyer",
        at: "2026-11-03T10:30:00Z",
        action: "update",
        changes: [
          { field: "Port", before: "Gibraltar", after: "Rotterdam" },
          { field: "Note", before: null, after: "Supercalifragilisticexpialidocious".repeat(2) },
        ],
      },
      {
        id: "2",
        actor: "Bob Buyer",
        at: "2026-11-02T09:00:00Z",
        action: "deactivate",
        changes: [],
      },
    ],
  },
} satisfies Meta<typeof HistoryList>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Empty: Story = { args: { entries: [] } };
