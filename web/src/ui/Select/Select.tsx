import * as RadixSelect from "@radix-ui/react-select";
import { Field } from "../Field/Field";
import styles from "../Field/Field.module.css";
import own from "./Select.module.css";

type SelectOption<T extends string> = { value: T; label: string; disabled?: boolean };

export type SelectProps<T extends string> = {
  id: string;
  label: string;
  value: T | "";
  options: SelectOption<T>[];
  onChange: (value: T) => void;
  error?: string;
  hint?: string;
  required?: boolean;
  disabled?: boolean;
};

export function Select<T extends string>({
  id,
  label,
  value,
  options,
  onChange,
  disabled,
  ...field
}: SelectProps<T>) {
  return (
    <Field id={id} label={label} {...field}>
      {(a11y) => (
        <RadixSelect.Root
          value={value}
          disabled={disabled}
          required={field.required}
          onValueChange={(v) => onChange(v as T)}
        >
          <RadixSelect.Trigger {...a11y} className={`${styles.input} ${own.trigger}`}>
            <RadixSelect.Value placeholder="Select…" />
            <RadixSelect.Icon aria-hidden="true">▾</RadixSelect.Icon>
          </RadixSelect.Trigger>
          <RadixSelect.Portal>
            <RadixSelect.Content className={own.content} position="popper" sideOffset={4}>
              <RadixSelect.Viewport>
                {options.map((o) => (
                  <RadixSelect.Item
                    key={o.value}
                    value={o.value}
                    disabled={o.disabled}
                    className={own.item}
                  >
                    <RadixSelect.ItemText>{o.label}</RadixSelect.ItemText>
                  </RadixSelect.Item>
                ))}
              </RadixSelect.Viewport>
            </RadixSelect.Content>
          </RadixSelect.Portal>
        </RadixSelect.Root>
      )}
    </Field>
  );
}
