import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { Select } from "./Select";

const options = [
  { value: "a", label: "Alpha" },
  { value: "b", label: "Beta" },
  { value: "c", label: "Gamma", disabled: true },
] as const;

describe("Select", () => {
  afterEach(cleanup);
  beforeAll(() => {
    // jsdom lacks the pointer/scroll APIs Radix Select uses.
    Element.prototype.hasPointerCapture = () => false;
    Element.prototype.setPointerCapture = () => undefined;
    Element.prototype.releasePointerCapture = () => undefined;
    Element.prototype.scrollIntoView = () => undefined;
  });

  it("[B1-R13] the label and error are associated with the trigger", () => {
    render(
      <Select
        id="s"
        label="Fuel"
        value=""
        options={[...options]}
        onChange={vi.fn()}
        error="Pick one"
        required
      />,
    );
    const trigger = screen.getByRole("combobox", { name: /Fuel/ });
    expect(trigger.getAttribute("aria-describedby")).toBe("s-error");
    expect(trigger.getAttribute("aria-invalid")).toBe("true");
    expect(trigger.textContent).toContain("Select…");
  });

  it("[B1-R13] choosing an option calls onChange; disabled options cannot be chosen", async () => {
    const onChange = vi.fn();
    render(<Select id="s" label="Fuel" value="a" options={[...options]} onChange={onChange} />);
    const trigger = screen.getByRole("combobox", { name: "Fuel" });
    expect(trigger.textContent).toContain("Alpha");
    await userEvent.click(trigger);
    await userEvent.click(await screen.findByRole("option", { name: "Gamma" }));
    expect(onChange).not.toHaveBeenCalled();
    await userEvent.click(await screen.findByRole("option", { name: "Beta" }));
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("[B4-R12] an empty option clears the value", async () => {
    const onChange = vi.fn();
    render(
      <Select
        id="s"
        label="Fuel"
        value="a"
        options={[...options]}
        onChange={onChange}
        emptyLabel="None"
      />,
    );
    await userEvent.click(screen.getByRole("combobox", { name: "Fuel" }));
    await userEvent.click(await screen.findByRole("option", { name: "None" }));
    expect(onChange).toHaveBeenCalledWith("");
  });
});
