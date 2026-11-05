import type { Meta, StoryObj } from "@storybook/react-vite";
import { within } from "@testing-library/dom";
import { AppShell } from "./AppShell";

const meta = {
  title: "UI/AppShell",
  component: AppShell,
  parameters: { layout: "fullscreen" },
  args: {
    productName: "Bunker Desk",
    user: { name: "Ada Lindqvist", roles: ["bunker_buyer", "viewer"] },
    banner: "Demo data only",
    current: "#inquiry",
    nav: [
      { href: "#worklist", label: "Work list", section: "Purchase" },
      { href: "#inquiry", label: "Inquiry", section: "Purchase" },
      { href: "#suppliers", label: "Suppliers", section: "Master data" },
      { href: "#reports", label: "Reports", section: "Master data", disabled: true },
    ],
    children: <p>Working pane</p>,
  },
} satisfies Meta<typeof AppShell>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const SignedOut: Story = { args: { user: null, nav: [], banner: undefined } };
// Opens the nav; the 400 px visual test shows the collapsed layout with this menu button.
export const MenuOpen: Story = {
  play: ({ canvasElement }) => {
    within(canvasElement).getByRole("button", { name: "Menu" }).click();
  },
};
