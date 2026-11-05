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
    ["", ""],
  ])("[B1-R14] normalizeDecimal keeps precision: %j -> %j", (input, value) => {
    expect(normalizeDecimal(input, 2)).toEqual({ value });
  });

  it.each(["12abc", "-", ",", "1,234", "1.234", "12.", "1.2,3", "1,5,", "1.2.3,4", "1,2,3"])(
    "[B1-R14] normalizeDecimal rejects %j",
    (input) => {
      expect(normalizeDecimal(input, 3)).toHaveProperty("error");
    },
  );

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
      .filter(([neg, int, frac]) => !(neg && int === "0" && frac === ""))
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

function Harness({ onValue }: { onValue?: (v: string) => void }) {
  const [v, setV] = useState("");
  return (
    <NumberField
      id="qty"
      label="Quantity"
      value={v}
      decimals={2}
      unit="MT"
      onChange={(x) => {
        setV(x);
        onValue?.(x);
      }}
    />
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

  it("[B1-R14] garbage paste shows a field error and leaves the value unchanged", async () => {
    const onValue = vi.fn();
    render(<Harness onValue={onValue} />);
    const input = screen.getByLabelText("Quantity");
    await userEvent.click(input);
    await userEvent.paste("12abc");
    expect(onValue).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toMatch(/Enter a number/);
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(input.getAttribute("aria-describedby")).toContain("qty-error");
    await userEvent.tab();
    expect(screen.getByRole("alert")).toBeTruthy();
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
