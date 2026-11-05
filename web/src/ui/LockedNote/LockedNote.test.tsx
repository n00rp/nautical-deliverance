import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { LockedNote } from "./LockedNote";

describe("LockedNote", () => {
  afterEach(cleanup);

  it("[B1-R13] locked note: says what is hidden for the role", () => {
    render(<LockedNote what="prices and offers" />);
    expect(screen.getByText("Hidden for your role: prices and offers")).toBeTruthy();
  });
});
