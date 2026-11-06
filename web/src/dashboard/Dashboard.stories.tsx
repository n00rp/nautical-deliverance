import type { Meta, StoryObj } from "@storybook/react-vite";
import type { Dashboard as Data } from "../dashboardApi";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { Dashboard } from "./Dashboard";
import { empty, full, operator } from "./testSupport";

const show = (data: Data): StoryObj => ({
  render: () => (
    <ToastProvider>
      <Dashboard api={{ getDashboard: () => Promise.resolve(data) }} />
      <ToastHost />
    </ToastProvider>
  ),
});

export default {
  title: "Dashboard/Dashboard",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

export const Full = show(full);
export const Empty = show(empty);
export const AsOperator = show(operator);
