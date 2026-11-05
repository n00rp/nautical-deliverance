import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { FieldError } from "../FieldError/FieldError";
import { FormSummary } from "./FormSummary";

describe("FormSummary", () => {
  afterEach(cleanup);

  it("[B1-R13] each summary link focuses its field", async () => {
    render(
      <>
        <FormSummary
          errors={[
            { fieldId: "a", message: "A is required" },
            { fieldId: "missing", message: "Gone" },
          ]}
        />
        <input id="a" aria-label="A" />
      </>,
    );
    expect(screen.getByText("2 problems to fix")).toBeTruthy();
    await userEvent.click(screen.getByRole("link", { name: "A is required" }));
    expect(document.activeElement?.id).toBe("a");
    await userEvent.click(screen.getByRole("link", { name: "Gone" }));
  });

  it("[B1-R13] singular title, and nothing when there are no errors", () => {
    const { container, rerender } = render(
      <FormSummary errors={[{ fieldId: "a", message: "m" }]} />,
    );
    expect(screen.getByText("1 problem to fix")).toBeTruthy();
    rerender(<FormSummary errors={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("[B1-R13] FieldError renders an alert with its id", () => {
    render(<FieldError id="x-error">Bad</FieldError>);
    expect(screen.getByRole("alert").id).toBe("x-error");
  });
});
