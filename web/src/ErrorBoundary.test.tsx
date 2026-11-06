import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "./ErrorBoundary";

afterEach(cleanup);

function Boom(): never {
  throw new Error("render failed");
}

describe("ErrorBoundary", () => {
  it("[B4-R12] a render error shows a reload message and is logged instead of blanking the app", () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert").textContent).toBe("Something went wrong — reload the page");
    expect(log).toHaveBeenCalled();
    log.mockRestore();
  });

  it("[B4-R12] renders children when nothing fails", () => {
    render(
      <ErrorBoundary>
        <p>fine</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("fine")).toBeTruthy();
  });
});
