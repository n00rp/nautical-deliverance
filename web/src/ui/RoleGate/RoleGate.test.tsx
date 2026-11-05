import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { RoleGate, type Role } from "./RoleGate";

const all: Role[] = ["admin", "bunker_buyer", "operator", "viewer"];

describe("RoleGate", () => {
  afterEach(cleanup);

  it("[B1-R13] role gate: shows children only when a held role is allowed (matrix)", () => {
    for (const held of all) {
      for (const allowed of all) {
        render(
          <RoleGate allow={[allowed]} roles={[held]} fallback={<span>no</span>}>
            <span>yes</span>
          </RoleGate>,
        );
        expect(screen.queryByText("yes") !== null, `${held}/${allowed}`).toBe(held === allowed);
        expect(screen.queryByText("no") !== null, `${held}/${allowed}`).toBe(held !== allowed);
        cleanup();
      }
    }
  });

  it("[B1-R13] role gate: any one of several roles is enough; none renders nothing", () => {
    const { container, rerender } = render(
      <RoleGate allow={["admin", "operator"]} roles={["viewer", "operator"]}>
        <span>yes</span>
      </RoleGate>,
    );
    expect(screen.getByText("yes")).toBeTruthy();
    rerender(
      <RoleGate allow={["admin"]} roles={[]}>
        <span>yes</span>
      </RoleGate>,
    );
    expect(container.textContent).toBe("");
  });
});
