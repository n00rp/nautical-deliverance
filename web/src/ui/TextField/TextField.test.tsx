import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TextField } from "./TextField";

describe("TextField", () => {
  afterEach(cleanup);

  it("[B1-R13] label, hint and error are associated with the input", async () => {
    const onChange = vi.fn();
    render(
      <TextField
        id="v"
        label="Vessel"
        value=""
        onChange={onChange}
        hint="IMO name"
        error="Required"
        required
      />,
    );
    const input = screen.getByLabelText(/Vessel/);
    expect(input.getAttribute("aria-describedby")).toBe("v-hint v-error");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(input.hasAttribute("required")).toBe(true);
    await userEvent.type(input, "A");
    expect(onChange).toHaveBeenCalledWith("A");
  });

  it("[B4-R12] rows turn the field into a text area with the same wiring", async () => {
    const onChange = vi.fn();
    render(
      <TextField id="n" label="Note" value="" onChange={onChange} rows={3} error="Required" />,
    );
    const area = screen.getByLabelText("Note");
    expect(area.tagName).toBe("TEXTAREA");
    expect(area.getAttribute("aria-invalid")).toBe("true");
    await userEvent.type(area, "A");
    expect(onChange).toHaveBeenCalledWith("A");
  });

  it("[B1-R13] a plain field has no description and no invalid flag", () => {
    render(<TextField id="v" label="Vessel" value="x" onChange={vi.fn()} disabled />);
    const input = screen.getByLabelText("Vessel");
    expect(input.hasAttribute("aria-describedby")).toBe(false);
    expect(input.hasAttribute("aria-invalid")).toBe(false);
    expect((input as HTMLInputElement).disabled).toBe(true);
  });
});
