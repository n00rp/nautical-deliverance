import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Button } from "./Button";

describe("Button", () => {
  afterEach(cleanup);

  it("[B1-R13] button states: disabled is not clickable", async () => {
    const onClick = vi.fn();
    render(
      <Button variant="primary" disabled onClick={onClick}>
        Save
      </Button>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onClick).not.toHaveBeenCalled();
  });

  it("[B1-R13] button states: loading is busy, labelled and not clickable", async () => {
    const onClick = vi.fn();
    render(
      <Button variant="secondary" loading onClick={onClick}>
        Save
      </Button>,
    );
    const button = screen.getByRole("button", { name: /Save/ });
    expect(button.getAttribute("aria-busy")).toBe("true");
    expect(button.textContent).toContain("Working");
    await userEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("[B1-R13] button states: defaults to type=button and is clickable", async () => {
    const onClick = vi.fn();
    render(
      <Button variant="ghost" onClick={onClick}>
        Go
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Go" });
    expect(button.getAttribute("type")).toBe("button");
    expect(button.hasAttribute("aria-busy")).toBe(false);
    await userEvent.click(button);
    expect(onClick).toHaveBeenCalledOnce();
  });
});
