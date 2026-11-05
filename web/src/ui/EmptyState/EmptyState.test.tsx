import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  afterEach(cleanup);

  it("[B1-R13] empty state: title, optional body and action", () => {
    const { rerender } = render(<EmptyState title="No offers yet" />);
    expect(screen.getByText("No offers yet")).toBeTruthy();
    rerender(
      <EmptyState
        title="No offers yet"
        body="Send an RFQ."
        action={<button type="button">Send</button>}
      />,
    );
    expect(screen.getByText("Send an RFQ.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Send" })).toBeTruthy();
  });
});
