import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { InlineConfirm } from "./InlineConfirm";

describe("InlineConfirm", () => {
  afterEach(cleanup);

  it("[B1-R13] inline confirm: needs two activations and never calls window.confirm", async () => {
    const onConfirm = vi.fn();
    const native = vi.spyOn(window, "confirm");
    render(
      <InlineConfirm label="Cancel inquiry" confirmLabel="Yes, cancel" onConfirm={onConfirm} />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Cancel inquiry" }));
    expect(onConfirm).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Yes, cancel" }));
    expect(onConfirm).toHaveBeenCalledOnce();
    expect(native).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Cancel inquiry" })).toBeTruthy();
  });

  it("[B1-R13] inline confirm: Cancel disarms without confirming", async () => {
    const onConfirm = vi.fn();
    render(
      <InlineConfirm
        label="Delete"
        confirmLabel="Really delete"
        tone="crit"
        onConfirm={onConfirm}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Delete" })).toBeTruthy();
  });
});
