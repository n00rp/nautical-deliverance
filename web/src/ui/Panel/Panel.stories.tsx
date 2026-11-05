import type { Meta, StoryObj } from "@storybook/react-vite";
import { Button } from "../Button/Button";
import { Panel } from "./Panel";

const meta = {
  title: "UI/Panel",
  component: Panel,
  args: { title: "Offer details", children: "Delivered grade VLSFO 0.5%, barge, 3 days validity." },
} satisfies Meta<typeof Panel>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const WithActions: Story = {
  args: {
    actions: <Button variant="secondary">Edit</Button>,
  },
};
