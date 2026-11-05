import type { Meta, StoryObj } from "@storybook/react-vite";
import { RoleGate } from "./RoleGate";

const meta = {
  title: "UI/RoleGate",
  component: RoleGate,
  args: {
    allow: ["admin", "bunker_buyer"],
    roles: ["bunker_buyer"],
    fallback: <p>Not available for your role.</p>,
    children: <p>Visible to buyers and admins.</p>,
  },
} satisfies Meta<typeof RoleGate>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Allowed: Story = {};
export const Fallback: Story = { args: { roles: ["viewer"] } };
