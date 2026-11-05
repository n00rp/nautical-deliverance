import type { Meta, StoryObj } from "@storybook/react-vite";
import { Button } from "../Button/Button";
import { EmptyState } from "./EmptyState";

const meta = {
  title: "UI/EmptyState",
  component: EmptyState,
  args: { title: "No offers yet" },
} satisfies Meta<typeof EmptyState>;
export default meta;
type Story = StoryObj<typeof meta>;

export const TitleOnly: Story = {};
export const WithBodyAndAction: Story = {
  args: {
    body: "Offers appear here once suppliers reply to the RFQ.",
    action: <Button variant="primary">Send RFQ</Button>,
  },
};
