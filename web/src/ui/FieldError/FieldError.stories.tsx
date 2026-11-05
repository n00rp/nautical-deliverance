import type { Meta, StoryObj } from "@storybook/react-vite";
import { FieldError } from "./FieldError";

const meta = {
  title: "UI/FieldError",
  component: FieldError,
  args: { id: "x-error", children: "Enter a number such as 1234.56" },
} satisfies Meta<typeof FieldError>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
