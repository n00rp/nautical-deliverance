import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api";
import type { Role } from "../ui/RoleGate/RoleGate";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { Nomination } from "./Nomination";
import { amendedNom, changedNom, draftNom, firstText, nominationApi, sentNom } from "./testSupport";

beforeAll(() => {
  // jsdom lacks the pointer/scroll APIs Radix Select uses.
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => undefined;
  Element.prototype.releasePointerCapture = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

type Api = ReturnType<typeof nominationApi>;

function setup(roles: Role[] = ["bunker_buyer"], api: Api = nominationApi()) {
  render(
    <ToastProvider>
      <Nomination inquiryId="i1" api={api} roles={roles} />
      <ToastHost />
    </ToastProvider>,
  );
  return api;
}

const buttons = () => screen.queryAllByRole("button").map((b) => b.textContent);

describe("Nomination actions per status and role", () => {
  it("[B5-R11] a buyer with a draft sees the preview, Mark sent and Withdraw draft", async () => {
    setup();
    expect(await screen.findByText(firstText.subject)).toBeTruthy();
    expect(buttons()).toEqual(["Copy text", "Mark sent", "Withdraw draft"]);
    expect(screen.queryByRole("button", { name: /Create nomination|Amend nomination/ })).toBeNull();
  });

  it.each<[string, Parameters<typeof nominationApi>, string]>([
    ["Winner selected", [[], "winner_selected"], "Create nomination"],
    ["Nominated", [[sentNom], "nominated"], "Amend nomination"],
  ])("[B5-R11] without a draft in %s the buyer can create one", async (_, args, label) => {
    setup(["bunker_buyer"], nominationApi(...args));
    expect(await screen.findByRole("button", { name: label })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Mark sent" })).toBeNull();
  });

  it("[B5-R11] a cancelled inquiry offers no new nomination", async () => {
    setup(["admin"], nominationApi([sentNom], "cancelled"));
    await screen.findByRole("table", { name: "Sent versions" });
    expect(screen.queryByRole("button", { name: /nomination/ })).toBeNull();
  });

  it("[B5-R11] a viewer reads the draft but has no actions", async () => {
    setup(["viewer"]);
    expect(await screen.findByText(firstText.subject)).toBeTruthy();
    expect(buttons()).toEqual(["Copy text"]);
    expect(screen.queryByRole("combobox", { name: "Contact" })).toBeNull();
  });

  it("[B5-R11] the operator has no access and nothing is requested", () => {
    const api = nominationApi();
    const spy = vi.spyOn(api, "listNominations");
    setup(["operator"], api);
    expect(screen.getByText(/Hidden for your role/)).toBeTruthy();
    expect(spy).not.toHaveBeenCalled();
  });
});

describe("Nomination preview and hand-off", () => {
  it("[B5-R11] the mail link is exactly the API value", async () => {
    setup();
    const link = await screen.findByRole("link", { name: "Open in e-mail" });
    expect(link.getAttribute("href")).toBe(firstText.mailto);
  });

  it("[B5-R11] Copy text writes exactly the body", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    setup();
    const copy = await screen.findByRole("button", { name: "Copy text" });
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    await userEvent.click(copy);
    expect(writeText).toHaveBeenCalledWith(firstText.body);
  });

  it("[B5-R11] an amendment draft shows the amended subject", async () => {
    setup(["bunker_buyer"], nominationApi([draftNom, sentNom], "nominated"));
    expect(await screen.findByText(/^Amended nomination \(2\) INQ-2611-001/)).toBeTruthy();
  });

  it("[B5-R11] lists the sent versions with a changed pill, and a row shows its frozen text", async () => {
    setup(["viewer"], nominationApi([amendedNom, changedNom], "nominated"));
    const table = await screen.findByRole("table", { name: "Sent versions" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[0] as HTMLElement).getByText("v2")).toBeTruthy();
    expect(within(table).getAllByText("Changed since sent")).toHaveLength(1);
    expect(within(rows[1] as HTMLElement).getByText("Changed since sent")).toBeTruthy();
    await userEvent.click(within(rows[1] as HTMLElement).getByText("v1"));
    const panel = await screen.findByRole("complementary");
    expect(await within(panel).findByText(/ETA 11 Nov 06:00 UTC/)).toBeTruthy();
  });
});

describe("Nomination changes", () => {
  it("[B5-R11] Mark sent needs a confirm, then the inquiry shows Nominated", async () => {
    const api = setup();
    const send = vi.spyOn(api, "markNominationSent");
    expect(await screen.findByText("Winner selected")).toBeTruthy();
    await userEvent.click(await screen.findByRole("button", { name: "Mark sent" }));
    expect(send).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Confirm sent" }));
    expect(send).toHaveBeenCalledWith("n3", 1);
    expect(await screen.findByText("Nominated")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Mark sent" })).toBeNull();
    expect(screen.getByRole("button", { name: "Amend nomination" })).toBeTruthy();
    expect(screen.getByRole("table", { name: "Sent versions" })).toBeTruthy();
  });

  it("[B5-R11] the in-flight guard sends once however often Confirm is hit", async () => {
    const api = nominationApi();
    let release = () => {};
    const send = vi.fn(
      (id: string, version: number) =>
        new Promise<Awaited<ReturnType<Api["markNominationSent"]>>>((resolve) => {
          release = () => {
            resolve(api.markNominationSent(id, version));
          };
        }),
    );
    setup(["bunker_buyer"], { ...api, markNominationSent: send });
    await userEvent.click(await screen.findByRole("button", { name: "Mark sent" }));
    await userEvent.dblClick(screen.getByRole("button", { name: "Confirm sent" }));
    expect(send).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Mark sent" }).hasAttribute("disabled")).toBe(true);
    release();
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Mark sent" })).toBeNull();
    });
  });

  it("[B5-R11] Withdraw draft needs a confirm and then offers a new draft", async () => {
    const api = setup();
    const withdraw = vi.spyOn(api, "withdrawNomination");
    await userEvent.click(await screen.findByRole("button", { name: "Withdraw draft" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm withdraw" }));
    expect(withdraw).toHaveBeenCalledWith("n3", 1);
    expect(await screen.findByRole("button", { name: "Create nomination" })).toBeTruthy();
  });

  it("[B5-R11] Create nomination makes a draft and shows its preview", async () => {
    const api = setup(["bunker_buyer"], nominationApi([], "winner_selected"));
    const create = vi.spyOn(api, "createNomination");
    await userEvent.click(await screen.findByRole("button", { name: "Create nomination" }));
    expect(create).toHaveBeenCalledWith("i1");
    expect(await screen.findByText(firstText.subject)).toBeTruthy();
  });

  it.each([
    ["mark-sent", "Mark sent", "Confirm sent", "markNominationSent", /Could not mark sent/],
    ["withdraw", "Withdraw draft", "Confirm withdraw", "withdrawNomination", /changed by someone/],
  ] as const)(
    "[B5-R11] a 409 on %s says the state changed and reloads",
    async (_, open, confirm, method, message) => {
      const api = nominationApi();
      const spy = vi.spyOn(api, "listNominations");
      setup(["bunker_buyer"], { ...api, [method]: () => Promise.reject(new ApiError(409)) });
      await userEvent.click(await screen.findByRole("button", { name: open }));
      await userEvent.click(screen.getByRole("button", { name: confirm }));
      expect(await screen.findByText(message)).toBeTruthy();
      await waitFor(() => {
        expect(spy).toHaveBeenCalledTimes(2);
      });
    },
  );

  it("[B5-R11] choosing another contact patches the draft with its version", async () => {
    const api = setup();
    const patch = vi.spyOn(api, "patchNomination");
    await userEvent.click(await screen.findByRole("combobox", { name: "Contact" }));
    await userEvent.click(await screen.findByRole("option", { name: /Beta Second/ }));
    expect(patch).toHaveBeenCalledWith("n3", 1, "Beta-2");
  });
});
