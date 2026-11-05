import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import { NumberField, type NumberFieldProps } from "./NumberField";

// Keeps the value in state so the stories can be typed into by hand.
function Stateful(props: NumberFieldProps) {
  const [value, setValue] = useState(props.value);
  return (
    <NumberField
      {...props}
      value={value}
      onChange={(v) => {
        setValue(v);
        props.onChange(v);
      }}
    />
  );
}

const meta = {
  title: "UI/NumberField",
  component: NumberField,
  render: (args) => <Stateful key={args.value} {...args} />,
  args: {
    id: "qty",
    label: "Quantity",
    value: "",
    decimals: 2,
    unit: "MT",
    onChange: () => undefined,
  },
  parameters: {
    docs: {
      description: {
        component:
          "Exact decimal text, never a JS number. Paste `1 234,56` or `1,234.56` and the value becomes `1234.56`. " +
          "Both `,` and `.` work as decimal separator when unambiguous. A lone separator followed by exactly 3 digits " +
          "(`1,234`) is ambiguous (thousands or decimals?) and is rejected with a request to clarify. " +
          "More decimals than allowed are rejected, never rounded. While the text is invalid the field reports " +
          '`onChange("")` and `onValidityChange(false)`, so a form must block submit until validity is true again.',
      },
    },
  },
} satisfies Meta<typeof NumberField>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = { args: { hint: "Up to 2 decimals" } };
export const Filled: Story = { args: { value: "12345678901234.56", required: true } };
export const PasteSpaceComma: Story = {
  name: "Paste 1 234,56",
  args: { value: "1234.56" },
};
export const PasteDotComma: Story = {
  name: "Paste 1,234.56",
  args: { value: "1234.56" },
};
export const Error: Story = {
  name: "Error: garbage paste",
  args: { value: "1234.56", error: "Enter a number such as 1234.56" },
};
export const Ambiguous: Story = {
  name: "Error: ambiguous 1,234",
  args: {
    error:
      "Ambiguous: one separator followed by 3 digits. Use a decimal point (1234.567) or no separator.",
  },
};
export const Disabled: Story = { args: { value: "10.50", disabled: true } };
export const Focus: Story = {
  play: ({ canvasElement }) => {
    canvasElement.querySelector<HTMLElement>("input, button")?.focus();
  },
};
