import type { Meta, StoryObj } from "@storybook/react-vite";
import { Select } from "./Select";

const options = [
  { value: "vlsfo", label: "VLSFO 0.5%" },
  { value: "mgo", label: "DMA 0.1%" },
  { value: "hsfo", label: "HSFO 3.5%", disabled: true },
];

const meta = {
  title: "UI/Select",
  component: Select<string>,
  args: { id: "fuel", label: "Fuel grade", value: "", options, onChange: () => undefined },
} satisfies Meta<typeof Select<string>>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Filled: Story = { args: { value: "mgo", required: true } };
export const Error: Story = { args: { error: "Choose a fuel grade" } };
export const Disabled: Story = { args: { value: "mgo", disabled: true } };
export const Focus: Story = {
  play: ({ canvasElement }) => {
    canvasElement.querySelector<HTMLElement>("input, button")?.focus();
  },
};
