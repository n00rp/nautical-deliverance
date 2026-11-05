import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastHost, ToastProvider, useToast } from "./Toast";

function Trigger({ tone }: { tone?: "crit" }) {
  const toast = useToast();
  return (
    <button
      type="button"
      onClick={() => {
        toast("Offer saved", tone);
      }}
    >
      go
    </button>
  );
}

const setup = (tone?: "crit") =>
  render(
    <ToastProvider>
      <Trigger tone={tone} />
      <ToastHost />
    </ToastProvider>,
  );

describe("Toast", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("[B1-R13] toast: host is a polite live region that announces messages", async () => {
    setup();
    const host = screen.getByRole("status");
    expect(host.getAttribute("aria-live")).toBe("polite");
    expect(host.textContent).toBe("");
    await userEvent.click(screen.getByRole("button", { name: "go" }));
    expect(host.textContent).toContain("Offer saved");
  });

  it("[B1-R13] toast: dismiss button and timeout remove it", async () => {
    setup("crit");
    await userEvent.click(screen.getByRole("button", { name: "go" }));
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText("Offer saved")).toBeNull();

    vi.useFakeTimers();
    act(() => {
      screen.getByRole("button", { name: "go" }).click();
    });
    expect(screen.getByText("Offer saved")).toBeTruthy();
    act(() => {
      vi.advanceTimersByTime(6000);
    });
    expect(screen.queryByText("Offer saved")).toBeNull();
  });

  it("[B1-R13] toast: useToast outside a provider fails loudly", () => {
    const quiet = vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => render(<ToastHost />)).toThrow("ToastProvider");
    quiet.mockRestore();
  });

  it("[B1-R13] toast: unmounting clears pending timers", () => {
    vi.useFakeTimers();
    const { unmount } = setup();
    act(() => {
      screen.getByRole("button", { name: "go" }).click();
    });
    expect(vi.getTimerCount()).toBe(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
