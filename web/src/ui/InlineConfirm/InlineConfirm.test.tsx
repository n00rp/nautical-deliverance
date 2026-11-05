import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { InlineConfirm } from "./InlineConfirm";

describe("InlineConfirm", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

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

  it("[B1-R13] inline confirm: focus leaving resets to idle", async () => {
    render(
      <>
        <InlineConfirm label="Delete" confirmLabel="Really delete" onConfirm={() => undefined} />
        <button type="button">outside</button>
      </>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Really delete" }));
    await userEvent.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("button", { name: "Really delete" })).not.toBeNull();
    await userEvent.tab();
    expect(screen.getByRole("button", { name: "Delete" })).toBeTruthy();
  });

  it("[B1-R13] inline confirm: resets after timeoutMs (default 8000)", () => {
    vi.useFakeTimers();
    render(
      <InlineConfirm label="Delete" confirmLabel="Really delete" onConfirm={() => undefined} />,
    );
    act(() => {
      screen.getByRole("button", { name: "Delete" }).click();
    });
    act(() => {
      vi.advanceTimersByTime(7999);
    });
    expect(screen.queryByRole("button", { name: "Really delete" })).not.toBeNull();
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(screen.getByRole("button", { name: "Delete" })).toBeTruthy();
  });
});
