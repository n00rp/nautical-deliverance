import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { ApiError, fetchMe } from "./api";
import { PRODUCT_NAME } from "./productName";

const auth = vi.hoisted(() => ({
  getUser: vi.fn(),
  signinRedirect: vi.fn(),
  signinRedirectCallback: vi.fn(),
}));
vi.mock("./auth", () => ({ userManager: auth }));
vi.mock("./api", async (orig) => ({ ...(await orig<typeof import("./api")>()), fetchMe: vi.fn() }));

const user = { access_token: "tok", expired: false };
const me = {
  user_id: "u-1",
  organization: { id: "o-1", name: "Acme Shipping" },
  roles: ["admin", "viewer"],
};

beforeEach(() => {
  vi.resetAllMocks();
});
afterEach(() => {
  cleanup();
  window.history.replaceState({}, "", "/");
});

describe("App", () => {
  it("[S0-R03] shows sign-in button when signed out", async () => {
    auth.getUser.mockResolvedValue(null);
    render(<App />);

    expect(screen.getByText("Loading…")).toBeTruthy();
    const button = await screen.findByRole("button", { name: "Sign in" });
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(PRODUCT_NAME);
    expect(document.title).toBe(PRODUCT_NAME);

    await userEvent.click(button);
    expect(auth.signinRedirect).toHaveBeenCalledOnce();
  });

  it("[S0-R03] shows user organization name and roles when signed in", async () => {
    auth.getUser.mockResolvedValue(user);
    vi.mocked(fetchMe).mockResolvedValue(me);
    render(<App />);

    expect(await screen.findByText("Acme Shipping")).toBeTruthy();
    expect(screen.getByText("admin, viewer")).toBeTruthy();
    expect(fetchMe).toHaveBeenCalledWith("tok");
  });

  it("[S0-R03] shows error message when /me fails", async () => {
    auth.getUser.mockResolvedValue(user);
    vi.mocked(fetchMe).mockRejectedValue(new ApiError(403));
    render(<App />);

    expect((await screen.findByRole("alert")).textContent).toContain("403");
    expect(screen.getByRole("heading", { level: 1 })).toBeTruthy();
  });

  it("[S0-R03] shows error message for non-API failures", async () => {
    auth.getUser.mockRejectedValue(new Error("boom"));
    render(<App />);

    expect((await screen.findByRole("alert")).textContent).toContain("boom");
  });

  it("[S0-R03] shows generic error for non-Error rejections", async () => {
    auth.getUser.mockRejectedValue("nope");
    render(<App />);

    expect((await screen.findByRole("alert")).textContent).toContain("Unknown error");
  });

  it("[S0-R03] treats an expired session as signed out", async () => {
    auth.getUser.mockResolvedValue({ ...user, expired: true });
    render(<App />);

    expect(await screen.findByRole("button", { name: "Sign in" })).toBeTruthy();
    expect(fetchMe).not.toHaveBeenCalled();
  });

  it("[S0-R03] completes the redirect callback and cleans the URL", async () => {
    window.history.replaceState({}, "", "/?code=abc&state=xyz");
    auth.signinRedirectCallback.mockResolvedValue(user);
    auth.getUser.mockResolvedValue(user);
    vi.mocked(fetchMe).mockResolvedValue(me);
    render(<App />);

    expect(await screen.findByText("Acme Shipping")).toBeTruthy();
    await waitFor(() => {
      expect(window.location.search).toBe("");
    });
    expect(auth.signinRedirectCallback).toHaveBeenCalledOnce();
  });
});
