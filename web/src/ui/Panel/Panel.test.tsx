import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Panel } from "./Panel";

describe("Panel", () => {
  afterEach(cleanup);

  it("[B1-R13] panel: titled region with actions and body", () => {
    render(
      <Panel title="Offer" actions={<button type="button">Act</button>}>
        body text
      </Panel>,
    );
    expect(screen.getByRole("region", { name: "Offer" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Act" })).toBeTruthy();
    expect(screen.getByText("body text")).toBeTruthy();
  });

  it("[B1-R13] panel: without title it is a plain group", () => {
    render(<Panel>just body</Panel>);
    expect(screen.queryByRole("region")).toBeNull();
  });
});
