import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import fc from "fast-check";
import { readFileSync } from "node:fs";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NumberField } from "./NumberField";
import { normalizeDecimal } from "./normalize";

describe("normalizeDecimal", () => {
  it.each([
    ["0.1", "0.1"],
    ["12345678901234.56", "12345678901234.56"],
    ["1 234,56", "1234.56"],
    ["1 234,56", "1234.56"],
    ["1,234.56", "1234.56"],
    ["1.234,56", "1234.56"],
    ["1,234,567", "1234567"],
    ["-12,5", "-12.5"],
    [".5", "0.5"],
    ["007", "7"],
    ["-0", "0"],
    ["-0.00", "0.00"],
    ["-0.10", "-0.10"],
    ["", ""],
  ])("[B1-R14] normalizeDecimal keeps precision: %j -> %j", (input, value) => {
    expect(normalizeDecimal(input, 2)).toEqual({ value });
  });

  it.each([
    "12abc",
    "-",
    ",",
    "1,234",
    "1.234",
    "12.",
    "1.2,3",
    "1,5,",
    "1.2.3,4",
    "1,2,3",
    "01,234",
    "01.234",
  ])("[B1-R14] normalizeDecimal rejects %j", (input) => {
    expect(normalizeDecimal(input, 3)).toHaveProperty("error");
  });

  it.each([
    ["0.123", "0.123"],
    ["0,125", "0.125"],
    [".125", "0.125"],
    ["-0,125", "-0.125"],
    ["00,123", "0.123"],
    ["00.125", "0.125"],
  ])("[B1-R14] a 0-led head is a decimal, never a thousands group: %j", (input, value) => {
    expect(normalizeDecimal(input, 3)).toEqual({ value });
  });

  it("[B4-R12] with dotIsDecimal a single point is the decimal point, a single comma is still ambiguous", () => {
    expect(normalizeDecimal("612.345", 3, true)).toEqual({ value: "612.345" });
    expect(normalizeDecimal("1,234.567", 3, true)).toEqual({ value: "1234.567" });
    expect(normalizeDecimal("612,345", 3, true)).toHaveProperty("error");
    expect(normalizeDecimal("1.234.567", 3, true)).toEqual({ value: "1234567" });
    expect(normalizeDecimal("612.345", 3)).toHaveProperty("error");
  });

  it("[B1-R14] normalizeDecimal refuses to round: too many decimals", () => {
    expect(normalizeDecimal("1.234", 2)).toHaveProperty("error");
    expect(normalizeDecimal("1,5", 0)).toEqual({ error: "Whole numbers only" });
  });

  it("[B1-R14] normalizeDecimal keeps precision: property, canonical input is returned as is", () => {
    const canonical = fc
      .tuple(
        fc.boolean(),
        fc.stringMatching(/^(0|[1-9]\d{0,24})$/),
        fc.option(fc.stringMatching(/^\d{1,2}$/), { nil: "" }),
      )
      .filter(([neg, int, frac]) => !(neg && int === "0" && /^0*$/.test(frac)))
      .map(([neg, int, frac]) => `${neg ? "-" : ""}${int}${frac ? `.${frac}` : ""}`);
    fc.assert(
      fc.property(canonical, (s) => {
        expect(normalizeDecimal(s, 2)).toEqual({ value: s });
        // The same number written with a comma gives the same result.
        expect(normalizeDecimal(s.replace(".", ","), 2)).toEqual({ value: s });
      }),
    );
  });

  it("[B1-R14] normalizeDecimal never uses a float (source scan)", () => {
    const src = readFileSync("src/ui/NumberField/normalize.ts", "utf8").replace(
      /\/\*[\s\S]*?\*\/|\/\/.*$/gm,
      "",
    );
    expect(src).not.toMatch(/\bNumber\b|parseFloat|parseInt|\bMath\.|\+\+|--|\*\*/);
  });
});

function Harness({
  onValue,
  onValid,
}: {
  onValue?: (v: string) => void;
  onValid?: (v: boolean) => void;
}) {
  const [v, setV] = useState("");
  return (
    <>
      <button type="button" onClick={() => setV("")}>
        reset
      </button>
      <NumberField
        id="qty"
        label="Quantity"
        value={v}
        decimals={2}
        unit="MT"
        onValidityChange={onValid}
        onChange={(x) => {
          setV(x);
          onValue?.(x);
        }}
      />
    </>
  );
}

describe("NumberField", () => {
  afterEach(cleanup);

  it("[B1-R14] paste of 1 234,56 and 1,234.56 is normalized to 1234.56", async () => {
    const onValue = vi.fn();
    render(<Harness onValue={onValue} />);
    const input = screen.getByLabelText("Quantity");
    await userEvent.click(input);
    await userEvent.paste("1 234,56");
    expect(onValue).toHaveBeenLastCalledWith("1234.56");
    await userEvent.clear(input);
    await userEvent.paste("1,234.56");
    expect(onValue).toHaveBeenLastCalledWith("1234.56");
    await userEvent.tab();
    expect((input as HTMLInputElement).value).toBe("1234.56");
  });

  it("[B1-R14] garbage paste shows a field error, clears the value and signals invalid", async () => {
    const onValue = vi.fn();
    const onValid = vi.fn();
    render(<Harness onValue={onValue} onValid={onValid} />);
    const input = screen.getByLabelText("Quantity");
    await userEvent.click(input);
    await userEvent.paste("12abc");
    expect(onValue).toHaveBeenLastCalledWith("");
    expect(onValid).toHaveBeenLastCalledWith(false);
    expect(screen.getByRole("alert").textContent).toMatch(/Enter a number/);
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(input.getAttribute("aria-describedby")).toContain("qty-error");
    await userEvent.tab();
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("[B1-R14] valid input after invalid signals valid again with the exact value", async () => {
    const onValue = vi.fn();
    const onValid = vi.fn();
    render(<Harness onValue={onValue} onValid={onValid} />);
    const input = screen.getByLabelText("Quantity");
    await userEvent.type(input, "1x");
    expect(onValid).toHaveBeenLastCalledWith(false);
    await userEvent.type(input, "{Backspace}2");
    expect(onValid).toHaveBeenLastCalledWith(true);
    expect(onValue).toHaveBeenLastCalledWith("12");
  });

  it("[B1-R14] a parent reset while the field has a draft replaces the draft", async () => {
    render(<Harness />);
    const input = screen.getByLabelText<HTMLInputElement>("Quantity");
    await userEvent.type(input, "5");
    expect(input.value).toBe("5");
    await userEvent.click(screen.getByRole("button", { name: "reset" }));
    expect(input.value).toBe("");
  });

  it("[B1-R14] a parent value that differs from an invalid draft replaces it and its error", () => {
    const { rerender } = render(
      <NumberField id="n" label="Amount" value="" decimals={2} onChange={vi.fn()} />,
    );
    const input = screen.getByLabelText<HTMLInputElement>("Amount");
    fireEvent.change(input, { target: { value: "12abc" } });
    expect(screen.getByRole("alert")).toBeTruthy();
    rerender(<NumberField id="n" label="Amount" value="7" decimals={2} onChange={vi.fn()} />);
    expect(input.value).toBe("7");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("[B1-R14] an unfinished trailing separator is not flagged until blur", () => {
    render(<Harness />);
    const input = screen.getByLabelText("Quantity");
    fireEvent.change(input, { target: { value: "12," } });
    expect(screen.queryByRole("alert")).toBeNull();
    fireEvent.blur(input);
    expect(screen.getByRole("alert")).toBeTruthy();
    fireEvent.change(input, { target: { value: "12,5" } });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("[B1-R14] label, unit and error are associated; external error wins", () => {
    render(
      <NumberField
        id="n"
        label="Amount"
        value="1"
        decimals={2}
        unit="MT"
        error="Too low"
        onChange={vi.fn()}
        required
      />,
    );
    const input = screen.getByRole("textbox", { name: /Amount/ });
    expect(input.getAttribute("aria-describedby")).toBe("n-error n-unit");
    expect(input.getAttribute("aria-required")).toBe("true");
    expect(screen.getByRole("alert").textContent).toBe("Too low");
  });
});
