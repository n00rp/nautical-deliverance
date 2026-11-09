import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api";
import { inquiry } from "../inquiries/pageSupport";
import type { Role } from "../ui/RoleGate/RoleGate";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { RfqLog } from "./RfqLog";
import { changedRfq, declinedRfq, draftRfq, logApi, preview, sentRfq } from "./testSupport";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const all = [draftRfq, sentRfq, declinedRfq, changedRfq];

function setup(roles: Role[] = ["bunker_buyer"], log = all, api = logApi(log)) {
  render(
    <ToastProvider>
      <RfqLog inquiryId="i1" api={api} roles={roles} />
      <ToastHost />
    </ToastProvider>,
  );
  return api;
}

const openRow = async (name: string) => {
  await userEvent.click(await screen.findByRole("cell", { name }));
  return screen.findByRole("complementary");
};
const buttons = (panel: HTMLElement) =>
  within(panel)
    .queryAllByRole("button")
    .map((b) => b.textContent);

describe("RfqLog", () => {
  it("[B3-R13] lists the columns and a row per RFQ, with the changed-since-sent pill", async () => {
    setup();
    const table = await screen.findByRole("table", { name: "RFQs" });
    const headers = within(table)
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    expect(headers).toEqual([
      "Recipient",
      "Contact",
      "Address",
      "Generated",
      "Sent",
      "Status",
      "Deadline",
      "Offer received",
      "Changed",
    ]);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(4);
    const alpha = within(rows[0] as HTMLElement);
    expect(alpha.getByText("alpha.primary@example.test")).toBeTruthy();
    expect(alpha.getByText("Draft")).toBeTruthy();
    expect(alpha.getByText("05 Nov 09:00 UTC · 10:00 local")).toBeTruthy();
    // A draft has no sent time and no offer yet.
    expect(alpha.getAllByText("—")).toHaveLength(2);
    expect(within(rows[1] as HTMLElement).getByText("Sent")).toBeTruthy();
    expect(within(rows[2] as HTMLElement).getByText("Declined")).toBeTruthy();
    expect(within(table).getAllByText("Changed since sent")).toHaveLength(1);
    expect(within(rows[3] as HTMLElement).getByText("Changed since sent")).toBeTruthy();
  });

  it("[B3-R13] shows the inquiry status and an empty log", async () => {
    setup(["bunker_buyer"], []);
    expect(await screen.findByText("No RFQs yet")).toBeTruthy();
    expect(screen.getByText("INQ-2611-001 — RFQs")).toBeTruthy();
    expect(screen.getByText("Draft")).toBeTruthy();
  });

  it.each([
    ["Alpha Marine", ["Close", "Mark sent", "Withdraw"]],
    ["Beta Marine", ["Close", "Mark declined"]],
    ["Gamma Marine", ["Close"]],
  ])("[B3-R13] a buyer sees the right actions for %s", async (name, expected) => {
    setup();
    const panel = await openRow(name);
    await within(panel).findByText("Open in e-mail");
    expect(buttons(panel).filter((b) => b !== "Copy text")).toEqual(expected);
  });

  it("[B3-R13] a viewer can read the preview and copy but not act", async () => {
    setup(["viewer"]);
    const panel = await openRow("Alpha Marine");
    await within(panel).findByText("Open in e-mail");
    expect(buttons(panel)).toEqual(["Close", "Copy text"]);
    expect(screen.queryByRole("link", { name: "Select suppliers" })).toBeNull();
  });

  it("[B4-R12] writers get Enter offer or Edit offer on a sent RFQ only", async () => {
    const received = {
      ...sentRfq,
      id: "r5",
      counterparty_name: "Eps Marine",
      offer_received: true,
    };
    setup(["bunker_buyer"], [draftRfq, sentRfq, received]);
    await openRow("Beta Marine");
    expect(screen.getByRole("link", { name: "Enter offer" }).getAttribute("href")).toBe(
      "#/inquiries/i1/rfqs/r1/offer",
    );
    await openRow("Eps Marine");
    expect(screen.getByRole("link", { name: "Edit offer" }).getAttribute("href")).toBe(
      "#/inquiries/i1/rfqs/r5/offer",
    );
    await openRow("Alpha Marine");
    expect(screen.queryByRole("link", { name: /offer$/ })).toBeNull();
  });

  it("[B3-R13] switching rows shows one preview, never the previous one beside it", async () => {
    const errors = vi.spyOn(console, "error");
    setup(["bunker_buyer"], [draftRfq, sentRfq]);
    const panel = await openRow("Beta Marine");
    await within(panel).findByText("Open in e-mail");
    await openRow("Alpha Marine");
    await within(panel).findByText("Mark sent");
    expect(screen.getAllByRole("link", { name: "Open in e-mail" })).toHaveLength(1);
    // Two siblings with the same key make React duplicate or drop children.
    expect(errors.mock.calls.flat().join(" ")).not.toContain("same key");
  });

  it("[B4-R12] a viewer gets no offer link", async () => {
    setup(["viewer"]);
    await openRow("Beta Marine");
    expect(screen.queryByRole("link", { name: /offer$/ })).toBeNull();
  });

  it("[B3-R13] an operator gets a locked note and no requests", () => {
    const api = logApi();
    const spy = vi.spyOn(api, "listRfqs");
    setup(["operator"], all, api);
    expect(screen.getByText("Hidden for your role: the RFQ log")).toBeTruthy();
    expect(spy).not.toHaveBeenCalled();
  });

  it("[B3-R13] Mark sent needs a confirm, sends one request on a double click and updates the inquiry", async () => {
    const api = logApi();
    let release: () => void = () => undefined;
    const real = api.markSent;
    const slow = vi.spyOn(api, "markSent").mockImplementation(
      (...args) =>
        new Promise((resolve) => {
          release = () => {
            void Promise.resolve(real(...args)).then(resolve);
          };
        }),
    );
    setup(["bunker_buyer"], all, api);
    const panel = await openRow("Alpha Marine");
    await userEvent.click(await within(panel).findByRole("button", { name: "Mark sent" }));
    expect(slow).not.toHaveBeenCalled();
    await userEvent.dblClick(within(panel).getByRole("button", { name: "Confirm sent" }));
    expect(slow).toHaveBeenCalledTimes(1);
    expect(slow).toHaveBeenCalledWith("r0", 1);
    release();
    // The log reloads: the draft is now sent and the inquiry is "RFQ sent".
    await waitFor(() => {
      expect(screen.getAllByText("RFQ sent").length).toBeGreaterThan(0);
    });
    expect(await screen.findByText("Marked sent")).toBeTruthy();
    expect(slow).toHaveBeenCalledTimes(1);
  });

  it("[B3-R13] the in-flight guard drops a second action while one is running", async () => {
    const api = logApi();
    const withdraw = vi.spyOn(api, "withdrawRfq").mockReturnValue(new Promise(() => undefined));
    const send = vi.spyOn(api, "markSent");
    setup(["bunker_buyer"], all, api);
    const panel = await openRow("Alpha Marine");
    await userEvent.click(await within(panel).findByRole("button", { name: "Withdraw" }));
    await userEvent.click(within(panel).getByRole("button", { name: "Confirm withdraw" }));
    expect(withdraw).toHaveBeenCalledWith("r0", 1);
    expect(
      within(panel).getByRole<HTMLButtonElement>("button", { name: "Mark sent" }).disabled,
    ).toBe(true);
    expect(send).not.toHaveBeenCalled();
  });

  it("[B3-R13] the busy ref alone drops a second confirm fired before React re-renders", async () => {
    const api = logApi();
    const send = vi.spyOn(api, "markSent").mockReturnValue(new Promise(() => undefined));
    setup(["bunker_buyer"], all, api);
    const panel = await openRow("Alpha Marine");
    await userEvent.click(await within(panel).findByRole("button", { name: "Mark sent" }));
    const confirm = within(panel).getByRole("button", { name: "Confirm sent" });
    act(() => {
      fireEvent.click(confirm);
      fireEvent.click(confirm);
    });
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("[B3-R13] with the preview failing, a draft can still be withdrawn", async () => {
    const api = logApi();
    vi.spyOn(api, "getPreview").mockRejectedValue(new Error("no preview"));
    const withdraw = vi.spyOn(api, "withdrawRfq");
    setup(["bunker_buyer"], all, api);
    const panel = await openRow("Alpha Marine");
    expect(await within(panel).findByText("no preview")).toBeTruthy();
    await userEvent.click(within(panel).getByRole("button", { name: "Withdraw" }));
    await userEvent.click(within(panel).getByRole("button", { name: "Confirm withdraw" }));
    await waitFor(() => {
      expect(withdraw).toHaveBeenCalledWith("r0", 1);
    });
  });

  it("[B3-R13] the deadline editor stays open across a reload, and a failed reload keeps the rows", async () => {
    const api = logApi();
    vi.spyOn(api, "markSent").mockRejectedValueOnce(
      new ApiError(422, [{ field: "response_deadline", message: "Deadline has passed" }]),
    );
    setup(["bunker_buyer"], all, api);
    const panel = await openRow("Alpha Marine");
    await userEvent.click(await within(panel).findByRole("button", { name: "Mark sent" }));
    await userEvent.click(within(panel).getByRole("button", { name: "Confirm sent" }));
    await within(panel).findByLabelText(/^New offer deadline/);
    // Another action elsewhere bumps the version and reloads: the editor must survive.
    vi.spyOn(api, "listRfqs").mockRejectedValueOnce(new Error("blip"));
    await userEvent.click(within(panel).getByRole("button", { name: "Withdraw" }));
    vi.spyOn(api, "withdrawRfq").mockRejectedValueOnce(new ApiError(409));
    await userEvent.click(within(panel).getByRole("button", { name: "Confirm withdraw" }));
    expect(await screen.findByText("blip")).toBeTruthy();
    expect(screen.getByRole("table", { name: "RFQs" })).toBeTruthy();
    expect(within(panel).getByLabelText(/^New offer deadline/)).toBeTruthy();
  });

  it("[B3-R13] Mark declined and Withdraw call their routes with the row version", async () => {
    const api = logApi();
    const decline = vi.spyOn(api, "declineRfq");
    const withdraw = vi.spyOn(api, "withdrawRfq");
    setup(["bunker_buyer"], all, api);
    let panel = await openRow("Beta Marine");
    await userEvent.click(await within(panel).findByRole("button", { name: "Mark declined" }));
    await userEvent.click(within(panel).getByRole("button", { name: "Confirm declined" }));
    await waitFor(() => {
      expect(decline).toHaveBeenCalledWith("r1", 2);
    });
    expect(await screen.findByText("Marked declined")).toBeTruthy();
    panel = await openRow("Alpha Marine");
    await userEvent.click(await within(panel).findByRole("button", { name: "Withdraw" }));
    await userEvent.click(within(panel).getByRole("button", { name: "Confirm withdraw" }));
    await waitFor(() => {
      expect(withdraw).toHaveBeenCalledWith("r0", 1);
    });
    expect(
      await screen.findByText("Withdrawn", { selector: "[role=status] *, [role=status]" }),
    ).toBeTruthy();
  });

  it("[B3-R13] a stale version toasts the conflict and reloads", async () => {
    const api = logApi();
    vi.spyOn(api, "markSent").mockRejectedValueOnce(new ApiError(409));
    const list = vi.spyOn(api, "listRfqs");
    setup(["bunker_buyer"], all, api);
    const panel = await openRow("Alpha Marine");
    await userEvent.click(await within(panel).findByRole("button", { name: "Mark sent" }));
    await userEvent.click(within(panel).getByRole("button", { name: "Confirm sent" }));
    expect(await screen.findByText(/changed by someone else/)).toBeTruthy();
    await waitFor(() => {
      expect(list).toHaveBeenCalledTimes(2);
    });
  });

  it("[B3-R13] a passed deadline on Mark sent asks for a new one and then saves it", async () => {
    const api = logApi();
    vi.spyOn(api, "markSent").mockRejectedValueOnce(
      new ApiError(422, [{ field: "response_deadline", message: "Deadline has passed" }]),
    );
    const patch = vi.spyOn(api, "patchRfq");
    setup(["bunker_buyer"], all, api);
    const panel = await openRow("Alpha Marine");
    await userEvent.click(await within(panel).findByRole("button", { name: "Mark sent" }));
    await userEvent.click(within(panel).getByRole("button", { name: "Confirm sent" }));
    const field = await within(panel).findByLabelText(/^New offer deadline/);
    expect(within(panel).getByText("Deadline has passed")).toBeTruthy();
    const save = within(panel).getByRole<HTMLButtonElement>("button", { name: "Save deadline" });
    expect(save.disabled).toBe(true);
    fireEvent.change(field, { target: { value: "2026-12-01T08:00" } });
    await userEvent.click(save);
    await waitFor(() => {
      expect(patch).toHaveBeenCalledWith("r0", 1, {
        response_deadline: "2026-12-01T08:00:00.000Z",
      });
    });
    expect(await screen.findByText("Deadline saved")).toBeTruthy();
    // The editor goes away with the reload; Mark sent works again on the new version.
    await waitFor(() => {
      expect(screen.queryByLabelText(/^New offer deadline/)).toBeNull();
    });
  });

  it("[B3-R13] the page links back and, for writers only, to supplier selection", async () => {
    setup();
    expect(
      (await screen.findByRole("link", { name: "Back to inquiry" })).getAttribute("href"),
    ).toBe("#/inquiries/i1");
    expect(screen.getByRole("link", { name: "Select suppliers" }).getAttribute("href")).toBe(
      "#/inquiries/i1/suppliers",
    );
  });

  it("[B3-R13] Select suppliers is offered only while the inquiry accepts RFQs", async () => {
    const api = logApi(all);
    vi.spyOn(api, "getInquiry").mockResolvedValue(inquiry({ status: "nominated" }));
    setup(["bunker_buyer"], all, api);
    await screen.findByRole("link", { name: "Back to inquiry" });
    expect(screen.queryByRole("link", { name: "Select suppliers" })).toBeNull();
  });

  it("[B3-R13] a failed load shows an error state", async () => {
    const api = logApi();
    vi.spyOn(api, "listRfqs").mockRejectedValue(new Error("down"));
    setup(["bunker_buyer"], all, api);
    expect(await screen.findByText("Could not load RFQs")).toBeTruthy();
    expect(await screen.findByText("down")).toBeTruthy();
  });
});

describe("mail handoff", () => {
  it("[B3-R12] the open link equals the API mailto and the block shows To, Subject and Body", async () => {
    setup();
    const panel = await openRow("Beta Marine");
    const link = await within(panel).findByRole("link", { name: "Open in e-mail" });
    expect(link.getAttribute("href")).toBe(preview.mailto);
    expect(within(panel).getByText(preview.to)).toBeTruthy();
    expect(within(panel).getByText(preview.subject)).toBeTruthy();
    expect(within(panel).getByText(/please quote 500 mt VLSFO 0.5% & MGO\./).tagName).toBe("PRE");
    expect(within(panel).queryByText(/Body too long/)).toBeNull();
  });

  it("[B3-R12] Copy text writes exactly the body and toasts", async () => {
    const writeText = vi.fn<(t: string) => Promise<void>>().mockResolvedValue();
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    setup();
    const panel = await openRow("Beta Marine");
    await userEvent.click(await within(panel).findByRole("button", { name: "Copy text" }));
    expect(writeText).toHaveBeenCalledWith(preview.body);
    expect(writeText.mock.calls[0]?.[0]).toBe(preview.body);
    expect(await screen.findByText("Copied")).toBeTruthy();
    vi.unstubAllGlobals();
  });

  it("[B3-R12] when the clipboard fails, the text is selected instead", async () => {
    const writeText = vi.fn<(t: string) => Promise<void>>().mockRejectedValue(new Error("denied"));
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    setup();
    const panel = await openRow("Beta Marine");
    await userEvent.click(await within(panel).findByRole("button", { name: "Copy text" }));
    expect(await screen.findByText(/the text is selected/)).toBeTruthy();
    expect(window.getSelection()?.toString()).toContain("please quote 500 mt VLSFO");
    vi.unstubAllGlobals();
  });

  it("[B3-R12] a body too long for the link says so", async () => {
    setup(["bunker_buyer"], all, logApi(all, { ...preview, body_in_link: false }));
    const panel = await openRow("Beta Marine");
    expect(
      await within(panel).findByText("Body too long for a mail link — use Copy text"),
    ).toBeTruthy();
  });

  it("[B3-R12] a failed preview shows the error", async () => {
    const api = logApi();
    vi.spyOn(api, "getPreview").mockRejectedValue(new Error("no preview"));
    setup(["bunker_buyer"], all, api);
    const panel = await openRow("Beta Marine");
    expect(await within(panel).findByText("no preview")).toBeTruthy();
  });
});
