import type { Meta, StoryObj } from "@storybook/react-vite";
import { FormSummary } from "./FormSummary";

const meta = {
  title: "UI/FormSummary",
  component: FormSummary,
  args: {
    errors: [
      { fieldId: "vessel", message: "Vessel name is required" },
      { fieldId: "qty", message: "Quantity must be a number" },
    ],
  },
} satisfies Meta<typeof FormSummary>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Single: Story = {
  args: { errors: [{ fieldId: "qty", message: "Quantity must be a number" }] },
};
