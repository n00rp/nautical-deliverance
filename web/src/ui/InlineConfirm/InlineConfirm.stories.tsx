import type { Meta, StoryObj } from "@storybook/react-vite";
import { InlineConfirm } from "./InlineConfirm";

const meta = {
  title: "UI/InlineConfirm",
  component: InlineConfirm,
  args: { label: "Cancel inquiry", confirmLabel: "Yes, cancel inquiry", onConfirm: () => {} },
} satisfies Meta<typeof InlineConfirm>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Idle: Story = {};
export const Armed: Story = {
  play: ({ canvasElement }) => {
    canvasElement.querySelector("button")?.click();
  },
};
export const ArmedCritical: Story = { args: { tone: "crit" }, play: Armed.play };
