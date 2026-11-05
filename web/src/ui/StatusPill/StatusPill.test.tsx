import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { StatusPill } from "./StatusPill";

describe("StatusPill", () => {
  afterEach(cleanup);

  it("[B1-R13] status pill: shows the status text with a tone", () => {
    render(<StatusPill status="Nominated" />);
    expect(screen.getByText("Nominated").getAttribute("data-tone")).toBe("ok");
  });

  it("[B1-R13] status pill: every status maps to a tone, tone variant takes children", () => {
    const all = [
      "Draft",
      "RFQ sent",
      "Offers received",
      "Winner selected",
      "Nominated",
      "Cancelled",
    ] as const;
    for (const s of all) render(<StatusPill status={s} />);
    expect(screen.getByText("Cancelled").getAttribute("data-tone")).toBe("crit");
    expect(screen.getByText("Winner selected").getAttribute("data-tone")).toBe("accent");
    render(<StatusPill tone="warn">Offer validity ends in 3 h</StatusPill>);
    expect(screen.getByText("Offer validity ends in 3 h").getAttribute("data-tone")).toBe("warn");
  });
});
