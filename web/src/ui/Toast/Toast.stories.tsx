import type { Meta, StoryObj } from "@storybook/react-vite";
import { useEffect } from "react";
import { ToastHost, ToastProvider, useToast, type ToastTone } from "./Toast";

function Fire({ tone }: { tone: ToastTone }) {
  const toast = useToast();
  useEffect(() => {
    toast(`A ${tone} message about the inquiry`, tone);
  }, [toast, tone]);
  return null;
}

function Demo({ tone }: { tone: ToastTone }) {
  return (
    // The transform makes the fixed host position against this box, so the screenshot contains it.
    <div style={{ transform: "translateZ(0)", height: "120px", width: "360px" }}>
      <ToastProvider>
        <Fire tone={tone} />
        <ToastHost />
        <p>Page content</p>
      </ToastProvider>
    </div>
  );
}

const meta = {
  title: "UI/Toast",
  component: Demo,
  args: { tone: "info" },
} satisfies Meta<typeof Demo>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Info: Story = {};
export const Ok: Story = { args: { tone: "ok" } };
export const Warn: Story = { args: { tone: "warn" } };
export const Crit: Story = { args: { tone: "crit" } };
