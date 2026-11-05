import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
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

vi.mock("./masterApi", async (orig) => {
  const { fakeApi } = await import("./admin/testSupport");
  return { ...(await orig<typeof import("./masterApi")>()), createMasterApi: () => fakeApi() };
});

vi.mock("./inquiryApi", async (orig) => ({
  ...(await orig<typeof import("./inquiryApi")>()),
  createInquiryApi: () => ({ listInquiries: () => Promise.resolve([]) }),
}));

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
  window.location.hash = "";
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

  it("[S0-R03] drops roles the web does not know yet without crashing", async () => {
    auth.getUser.mockResolvedValue(user);
    vi.mocked(fetchMe).mockResolvedValue({ ...me, roles: ["legacy_role"] });
    render(<App />);

    expect(await screen.findByText("Acme Shipping")).toBeTruthy();
    expect(screen.queryByText("legacy_role")).toBeNull();
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

  it("[S0-R03] shows sign-in button with error so user can recover", async () => {
    auth.getUser.mockResolvedValue(user);
    vi.mocked(fetchMe).mockRejectedValue(new ApiError(401));
    render(<App />);

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeTruthy();
  });

  it("[S0-R03] cleans callback URL even when callback fails", async () => {
    window.history.replaceState({}, "", "/?code=abc&state=xyz");
    auth.signinRedirectCallback.mockRejectedValue(new Error("bad code"));
    render(<App />);

    expect((await screen.findByRole("alert")).textContent).toContain("bad code");
    expect(window.location.search).toBe("");
  });

  it("[S0-R03] shows message when identity provider returns an error", async () => {
    window.history.replaceState({}, "", "/?error=access_denied&state=xyz");
    render(<App />);

    expect((await screen.findByRole("alert")).textContent).toBe("Sign-in was cancelled or denied.");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeTruthy();
    expect(window.location.search).toBe("");
    expect(auth.signinRedirectCallback).not.toHaveBeenCalled();
  });

  it("[S0-R03] runs the callback exactly once under StrictMode", async () => {
    window.history.replaceState({}, "", "/?code=abc&state=xyz");
    auth.signinRedirectCallback.mockResolvedValue(user);
    auth.getUser.mockResolvedValue(user);
    vi.mocked(fetchMe).mockResolvedValue(me);
    render(
      <StrictMode>
        <App />
      </StrictMode>,
    );

    expect(await screen.findByText("Acme Shipping")).toBeTruthy();
    expect(auth.signinRedirectCallback).toHaveBeenCalledOnce();
  });
});

describe("App master data", () => {
  it("[B1-R11] signed-in users get the Master data nav and hash routing to the pages", async () => {
    auth.getUser.mockResolvedValue(user);
    vi.mocked(fetchMe).mockResolvedValue(me);
    window.location.hash = "#/admin/ports";
    render(<App />);

    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(nav.querySelectorAll("a")).toHaveLength(8);
    expect(nav.querySelector("a")?.textContent).toBe("Inquiries");
    expect(screen.getByText("Master data")).toBeTruthy();
    expect(await screen.findByRole("heading", { name: "Ports" })).toBeTruthy();
    expect(nav.querySelector("[aria-current=page]")?.textContent).toBe("Ports");
  });

  it("[B1-R11] an unknown route points the signed-in user at the menu", async () => {
    auth.getUser.mockResolvedValue(user);
    vi.mocked(fetchMe).mockResolvedValue(me);
    window.location.hash = "#/nowhere";
    render(<App />);

    expect(await screen.findByText(/Choose a master-data page/)).toBeTruthy();
  });
});

describe("App inquiries", () => {
  it("[B2-R12] the work list is the start page", async () => {
    auth.getUser.mockResolvedValue(user);
    vi.mocked(fetchMe).mockResolvedValue(me);
    render(<App />);

    expect(await screen.findByRole("heading", { name: "Inquiries" })).toBeTruthy();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(nav.querySelector("[aria-current=page]")?.textContent).toBe("Inquiries");
  });

  it("[B2-R12] an inquiry id route shows the placeholder until the form exists", async () => {
    auth.getUser.mockResolvedValue(user);
    vi.mocked(fetchMe).mockResolvedValue(me);
    window.location.hash = "#/inquiries/new";
    render(<App />);

    expect(await screen.findByText(/not available yet/)).toBeTruthy();
  });
});
