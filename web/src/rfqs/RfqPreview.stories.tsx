import type { Meta, StoryObj } from "@storybook/react-vite";
import type { RfqPreview as Preview } from "../rfqApi";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { RfqPreview } from "./RfqPreview";
import { draftRfq, preview } from "./testSupport";

function Story({ msg }: { msg: Preview }) {
  return (
    <ToastProvider>
      <div style={{ maxWidth: "26rem" }}>
        <RfqPreview rfq={draftRfq} api={{ getPreview: () => Promise.resolve(msg) }} />
      </div>
      <ToastHost />
    </ToastProvider>
  );
}

const meta = { title: "RFQs/RfqPreview" } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = { render: () => <Story msg={preview} /> };
export const BodyTooLong: Story = {
  render: () => <Story msg={{ ...preview, body_in_link: false }} />,
};
