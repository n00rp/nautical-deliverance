import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Checkbox } from "./Checkbox";

describe("Checkbox", () => {
  afterEach(cleanup);

  it("[B1-R14] the label names the checkbox and clicking it toggles", async () => {
    const onChange = vi.fn();
    render(<Checkbox id="c" label="Confirm" checked={false} onChange={onChange} />);
    await userEvent.click(screen.getByText("Confirm"));
    expect(onChange).toHaveBeenCalledWith(true);
    expect(screen.getByRole("checkbox", { name: "Confirm" })).toBeTruthy();
  });

  it("[B1-R14] disabled checkbox does not toggle", async () => {
    const onChange = vi.fn();
    render(<Checkbox id="c" label="Confirm" checked disabled onChange={onChange} />);
    await userEvent.click(screen.getByRole("checkbox"));
    expect(onChange).not.toHaveBeenCalled();
  });
});
