import type { Meta, StoryObj } from "@storybook/react-vite";
import { DateTimeField } from "./DateTimeField";

const meta = {
  title: "UI/DateTimeField",
  component: DateTimeField,
  args: {
    id: "eta",
    label: "ETA",
    valueUtc: "",
    timeZone: "Europe/Amsterdam",
    onChange: () => undefined,
  },
} satisfies Meta<typeof DateTimeField>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Filled: Story = { args: { valueUtc: "2026-11-12T06:00:00.000Z", required: true } };
export const Error: Story = {
  args: { valueUtc: "2026-11-12T06:00:00.000Z", error: "ETA must be after the order date" },
};
export const Disabled: Story = { args: { valueUtc: "2026-11-12T06:00:00.000Z", disabled: true } };
export const Focus: Story = {
  play: ({ canvasElement }) => {
    canvasElement.querySelector<HTMLElement>("input, button")?.focus();
  },
};
