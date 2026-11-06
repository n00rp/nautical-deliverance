import type { FieldIssue } from "../api";
import { Button } from "../ui/Button/Button";
import { NumberField } from "../ui/NumberField/NumberField";
import { Select } from "../ui/Select/Select";
import { StatusPill } from "../ui/StatusPill/StatusPill";
import { TextField } from "../ui/TextField/TextField";
import css from "./Inquiry.module.css";
import { issueFor, MAX_LINES, newLine, type LineValues, type Unit } from "./formModel";

export type Opt = { value: string; label: string };

export type LinesEditorProps = {
  lines: LineValues[];
  products: Opt[];
  isos: Opt[];
  /** Unit a product is normally bought in, by product id. */
  defaultUnits: Record<string, Unit>;
  issues: FieldIssue[];
  /** Server warnings by line index. */
  warnings: Record<number, string[]>;
  /** Nothing can be edited (read-only role or locked after Draft). */
  disabled: boolean;
  onChange: (lines: LineValues[]) => void;
};

const UNITS: { value: Unit; label: string }[] = [
  { value: "mt", label: "mt" },
  { value: "m3", label: "m³" },
];

export function LinesEditor({
  lines,
  products,
  isos,
  defaultUnits,
  issues,
  warnings,
  disabled,
  onChange,
}: LinesEditorProps) {
  const update = (i: number, patch: Partial<LineValues>) => {
    onChange(lines.map((l, at) => (at === i ? { ...l, ...patch } : l)));
  };
  // Switching to mt clears the density: an mt line must not carry one (Review Focus 3).
  const setUnit = (i: number, unit: Unit) => {
    update(i, unit === "mt" ? { unit, density: "" } : { unit });
  };
  // The first product chosen on a line brings its usual unit.
  const setProduct = (i: number, l: LineValues, product_id: string) => {
    const unit = l.product_id === "" ? defaultUnits[product_id] : undefined;
    update(i, { product_id, ...(unit === "mt" ? { unit, density: "" } : unit ? { unit } : {}) });
  };

  return (
    <div className={css.lines}>
      {lines.map((l, i) => {
        const id = (name: string) => `line-${String(i)}-${name}`;
        const err = (name: string) => issueFor(issues, `lines[${String(i)}].${name}`);
        return (
          <div key={l.key} role="group" aria-label={`Line ${String(i + 1)}`} className={css.line}>
            <Select
              id={id("product_id")}
              label="Product"
              required
              value={l.product_id}
              options={products}
              disabled={disabled}
              error={err("product_id")}
              onChange={(v) => {
                setProduct(i, l, v);
              }}
            />
            <NumberField
              id={id("quantity")}
              label="Quantity"
              required
              decimals={3}
              value={l.quantity}
              disabled={disabled}
              error={err("quantity")}
              onChange={(v) => {
                update(i, { quantity: v });
              }}
            />
            <Select
              id={id("unit")}
              label="Unit"
              value={l.unit}
              options={UNITS}
              disabled={disabled}
              error={err("unit")}
              onChange={(v) => {
                setUnit(i, v);
              }}
            />
            {l.unit === "m3" && (
              <NumberField
                id={id("density")}
                label="Density (kg/m³)"
                decimals={1}
                value={l.density}
                disabled={disabled}
                error={err("density")}
                onChange={(v) => {
                  update(i, { density: v });
                }}
              />
            )}
            <Select
              id={id("iso_spec_version_id")}
              label="ISO spec version"
              required
              value={l.iso_spec_version_id}
              options={isos}
              disabled={disabled}
              error={err("iso_spec_version_id")}
              onChange={(v) => {
                update(i, { iso_spec_version_id: v });
              }}
            />
            <TextField
              id={id("spec_notes")}
              label="Spec notes"
              hint="Sent to suppliers in the RFQ"
              value={l.spec_notes}
              disabled={disabled}
              error={err("spec_notes")}
              onChange={(v) => {
                update(i, { spec_notes: v });
              }}
            />
            <div className={css.notes}>
              {l.unit === "m3" && l.density === "" && (
                <StatusPill tone="warn">Not in total until density is given</StatusPill>
              )}
              {(warnings[i] ?? []).map((m) => (
                <StatusPill key={m} tone="warn">
                  {m}
                </StatusPill>
              ))}
              {!disabled && lines.length > 1 && (
                <Button
                  variant="ghost"
                  onClick={() => {
                    onChange(lines.filter((_, at) => at !== i));
                  }}
                >
                  {`Remove line ${String(i + 1)}`}
                </Button>
              )}
            </div>
          </div>
        );
      })}
      {!disabled && (
        <div>
          <Button
            variant="secondary"
            disabled={lines.length >= MAX_LINES}
            onClick={() => {
              onChange([...lines, newLine()]);
            }}
          >
            Add line
          </Button>
        </div>
      )}
    </div>
  );
}
