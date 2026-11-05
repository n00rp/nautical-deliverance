import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DetailPanel } from "./DetailPanel";

describe("DetailPanel", () => {
  afterEach(cleanup);

  it("[B1-R13] detail panel: closed renders nothing", () => {
    render(
      <DetailPanel title="Offer" open={false} onClose={() => undefined}>
        x
      </DetailPanel>,
    );
    expect(screen.queryByRole("complementary")).toBeNull();
  });

  it("[B1-R13] detail panel: labelled non-modal region closed by button and Escape", async () => {
    const onClose = vi.fn();
    render(
      <DetailPanel title="Offer" open onClose={onClose}>
        details
      </DetailPanel>,
    );
    const aside = screen.getByRole("complementary", { name: "Offer" });
    expect(aside.hasAttribute("aria-modal")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    screen.getByRole("button", { name: "Close" }).focus();
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(2);
    await userEvent.keyboard("a");
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("[B1-R13] detail panel: closing returns focus to the opener or returnFocusRef", () => {
    const { rerender } = render(
      <>
        <button type="button">opener</button>
        <DetailPanel title="Offer" open={false} onClose={() => undefined}>
          x
        </DetailPanel>
      </>,
    );
    const opener = screen.getByRole("button", { name: "opener" });
    opener.focus();
    const ui = (open: boolean, ref?: React.RefObject<HTMLElement | null>) => (
      <>
        <button type="button">opener</button>
        <button type="button">other</button>
        <DetailPanel title="Offer" open={open} onClose={() => undefined} returnFocusRef={ref}>
          x
        </DetailPanel>
      </>
    );
    rerender(ui(true));
    screen.getByRole("button", { name: "Close" }).focus();
    rerender(ui(false));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "opener" }));
    const ref = createRef<HTMLElement>();
    (ref as { current: HTMLElement | null }).current = screen.getByRole("button", {
      name: "other",
    });
    rerender(ui(true, ref));
    screen.getByRole("button", { name: "Close" }).focus();
    rerender(ui(false, ref));
    expect(document.activeElement).toBe(ref.current);
  });
});
