import type { Meta, StoryObj } from "@storybook/react-vite";
import { LockedNote } from "./LockedNote";

const meta = {
  title: "UI/LockedNote",
  component: LockedNote,
  args: { what: "prices, offers and decision rationale" },
} satisfies Meta<typeof LockedNote>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
