import type { Meta, StoryObj } from "@storybook/react-vite";
import { TextField } from "./TextField";

const meta = {
  title: "UI/TextField",
  component: TextField,
  args: { id: "vessel", label: "Vessel name", value: "", onChange: () => undefined },
} satisfies Meta<typeof TextField>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = { args: { hint: "As on the registry certificate" } };
export const Filled: Story = { args: { value: "MV Nordic Star", required: true } };
export const Error: Story = { args: { value: "??", error: "Use letters and digits only" } };
export const Disabled: Story = { args: { value: "MV Nordic Star", disabled: true } };
export const Focus: Story = {
  play: ({ canvasElement }) => {
    canvasElement.querySelector<HTMLElement>("input, button")?.focus();
  },
};
