import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api";
import type { OfferApi } from "../offerApi";
import type { Role } from "../ui/RoleGate/RoleGate";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { Comparison, type ComparisonProps } from "./Comparison";
import {
  compareApi,
  completeOnly,
  decided,
  offersInquiry,
  partialAndExpired,
  tie,
} from "./comparisonSupport";

beforeAll(() => {
  // jsdom lacks the pointer/scroll APIs Radix Select uses.
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => undefined;
  Element.prototype.releasePointerCapture = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
});

afterEach(cleanup);

function setup(api: ComparisonProps["api"], roles: Role[] = ["bunker_buyer"]) {
  render(
    <ToastProvider>
      <Comparison inquiryId="i1" api={api} roles={roles} />
      <ToastHost />
    </ToastProvider>,
  );
}

const select = () => vi.fn<OfferApi["selectWinner"]>().mockResolvedValue(offersInquiry());
const row = async (name: string) => screen.findByRole("row", { name: new RegExp(name) });
const winnerButton = (r: HTMLElement) => within(r).getByRole("button", { name: "Select winner" });

describe("Comparison", () => {
  it("[B4-R12] the lowest row is highlighted and pilled, the others show their distance to it", async () => {
    setup(compareApi(completeOnly));
    const alpha = await row("Alpha Marine");
    expect(alpha.hasAttribute("data-highlight")).toBe(true);
    expect(within(alpha).getByText("Lowest")).toBeTruthy();
    expect(within(alpha).getByText("USD 380,000.00")).toBeTruthy();
    const beta = await row("Beta Marine");
    expect(beta.hasAttribute("data-highlight")).toBe(false);
    expect(within(beta).queryByText("Lowest")).toBeNull();
    expect(within(beta).getByText("+USD 10,722.50")).toBeTruthy();
    expect(within(await row("Gamma Bunkers")).getByText("Gulf Fuel Terminal")).toBeTruthy();
  });

  it("[B4-R12] offers with the same total are all the lowest", async () => {
    setup(compareApi(tie));
    expect((await row("Alpha Marine")).hasAttribute("data-highlight")).toBe(true);
    expect((await row("Beta Marine")).hasAttribute("data-highlight")).toBe(true);
    expect(screen.getAllByText("Lowest").length).toBe(2);
  });

  it("[B4-R12] a partial offer is tagged, an expiring one warns and an expired one is critical", async () => {
    setup(compareApi(partialAndExpired));
    expect(within(await row("Delta Oil")).getByText("Partial 1 of 2")).toBeTruthy();
    const soon = within(await row("Delta Oil")).getByText("Expires in less than 24 h");
    expect(soon.getAttribute("data-tone")).toBe("warn");
    const expired = within(await row("Echo Fuels")).getByText("Expired");
    expect(expired.getAttribute("data-tone")).toBe("crit");
    expect(within(await row("Alpha Marine")).getByText("Complete")).toBeTruthy();
    // Echo is cheaper but cannot be selected, so Alpha is the lowest (Ruling R5).
    expect((await row("Alpha Marine")).hasAttribute("data-highlight")).toBe(true);
    expect((await row("Echo Fuels")).hasAttribute("data-highlight")).toBe(false);
  });

  it("[B4-R12] cheaper expired and declined rows show no delta and a negative delta does not crash", async () => {
    const data = structuredClone(partialAndExpired); // engine-shaped: null deltas (R7)
    expect(data.rows.find((r) => r.offer_id === "oe")?.delta_to_lowest).toBeNull();
    expect(data.rows.find((r) => r.offer_id === "of")?.delta_to_lowest).toBeNull();
    setup(compareApi(data));
    for (const name of ["Echo Fuels", "Foxtrot Supply"]) {
      expect((await row(name)).textContent).not.toMatch(/\+USD|USD -/);
    }
    cleanup();
    data.rows.find((r) => r.offer_id === "oe")!.delta_to_lowest = "-25000.00"; // defensive
    setup(compareApi(data));
    expect(within(await row("Echo Fuels")).getByText("USD -25,000.00")).toBeTruthy();
  });

  it("[B4-R12] the detail panel shows the worked calculation, the fixed costs and the total", async () => {
    const data = structuredClone(completeOnly);
    const beta = data.rows.find((r) => r.offer_id === "ob")!;
    beta.barging_cost = "1200.00";
    beta.payment_terms = "30 days";
    beta.lines[1] = {
      ...beta.lines[1]!,
      qty_mt: "102.000",
      price_per_mt: "845.5",
      line_cost: "86241.00",
    };
    setup(compareApi(data));
    await userEvent.click(await row("Beta Marine"));
    const panel = screen.getByRole("complementary", { name: "Offer from Beta Marine" });
    expect(within(panel).getByText("500.000 mt × USD 612.345 = USD 306,172.50")).toBeTruthy();
    expect(within(panel).getByText("102.000 mt × USD 845.500 = USD 86,241.00")).toBeTruthy();
    expect(within(panel).getByText("USD 1,200.00")).toBeTruthy();
    expect(within(panel).getByText("Payment terms: 30 days")).toBeTruthy();
    expect(within(panel).getByText("USD 390,722.50")).toBeTruthy();
  });

  it("[B4-R12] a line without a price says why it is not in the total", async () => {
    setup(compareApi(partialAndExpired));
    await userEvent.click(await row("Delta Oil"));
    expect(screen.getByText("not in total: no price")).toBeTruthy();
  });

  it("[B4-R12] the lowest offer is selected with one confirmation and no form", async () => {
    const api = { ...compareApi(completeOnly), selectWinner: select() };
    setup(api);
    await userEvent.click(winnerButton(await row("Alpha Marine")));
    await userEvent.click(screen.getByRole("button", { name: "Confirm winner" }));
    await waitFor(() => {
      expect(api.selectWinner).toHaveBeenCalledWith("i1", 4, { offer_id: "oa" });
    });
    expect(screen.queryByRole("form", { name: "Selection rationale" })).toBeNull();
    expect(await screen.findByText("Winner selected")).toBeTruthy();
  });

  it("[B4-R12] a non-lowest offer needs a reason, and the reason other needs a note", async () => {
    const api = { ...compareApi(completeOnly), selectWinner: select() };
    setup(api);
    await userEvent.click(winnerButton(await row("Beta Marine")));
    const form = await screen.findByRole("form", { name: "Selection rationale" });

    await userEvent.click(within(form).getByRole("button", { name: "Confirm selection" }));
    expect(within(form).getAllByText("Choose why this offer is selected").length).toBeGreaterThan(
      0,
    );
    expect(api.selectWinner).not.toHaveBeenCalled();

    await userEvent.click(within(form).getByRole("combobox", { name: /Reason/ }));
    await userEvent.click(await screen.findByRole("option", { name: "Other" }));
    await userEvent.click(within(form).getByRole("button", { name: "Confirm selection" }));
    expect(within(form).getAllByText("Describe the reason").length).toBeGreaterThan(0);
    expect(api.selectWinner).not.toHaveBeenCalled();

    await userEvent.type(within(form).getByLabelText(/Note/), "Only supplier with a barge");
    await userEvent.click(within(form).getByRole("button", { name: "Confirm selection" }));
    await waitFor(() => {
      expect(api.selectWinner).toHaveBeenCalledWith("i1", 4, {
        offer_id: "ob",
        reason: "other",
        note: "Only supplier with a barge",
      });
    });
  });

  it("[B4-R12] a reason other than other needs no note", async () => {
    const api = { ...compareApi(completeOnly), selectWinner: select() };
    setup(api);
    await userEvent.click(winnerButton(await row("Gamma Bunkers")));
    await userEvent.click(await screen.findByRole("combobox", { name: /Reason/ }));
    await userEvent.click(await screen.findByRole("option", { name: "Reliability" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm selection" }));
    await waitFor(() => {
      expect(api.selectWinner).toHaveBeenCalledWith("i1", 4, {
        offer_id: "og",
        reason: "reliability",
      });
    });
  });

  it("[B4-R12] the engine's 422 lands on the reason field", async () => {
    const api = {
      ...compareApi(completeOnly),
      selectWinner: vi
        .fn<OfferApi["selectWinner"]>()
        .mockRejectedValue(
          new ApiError(422, [{ field: "offer_id", message: "Offer has expired" }]),
        ),
    };
    setup(api);
    await userEvent.click(winnerButton(await row("Beta Marine")));
    await userEvent.click(await screen.findByRole("combobox", { name: /Reason/ }));
    await userEvent.click(await screen.findByRole("option", { name: "Timing" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm selection" }));
    expect((await screen.findAllByText("Offer has expired")).length).toBeGreaterThan(0);
    expect(screen.getByRole("combobox", { name: /Reason/ }).getAttribute("aria-invalid")).toBe(
      "true",
    );
  });

  it("[B4-R12] a stale version reloads the comparison", async () => {
    const getComparison = vi.fn(() => Promise.resolve(completeOnly));
    const api = {
      ...compareApi(completeOnly),
      getComparison,
      selectWinner: vi.fn<OfferApi["selectWinner"]>().mockRejectedValue(new ApiError(409)),
    };
    setup(api);
    await userEvent.click(winnerButton(await row("Alpha Marine")));
    await userEvent.click(screen.getByRole("button", { name: "Confirm winner" }));
    await waitFor(() => {
      expect(getComparison).toHaveBeenCalledTimes(2);
    });
  });

  it("[B4-R12] a second selection while one is in flight is not sent", async () => {
    let release = () => {};
    const api = {
      ...compareApi(completeOnly),
      selectWinner: vi.fn<OfferApi["selectWinner"]>().mockImplementation(
        () =>
          new Promise((resolve) => {
            release = () => {
              resolve(offersInquiry());
            };
          }),
      ),
    };
    setup(api);
    await userEvent.click(winnerButton(await row("Alpha Marine")));
    await userEvent.click(screen.getByRole("button", { name: "Confirm winner" }));
    await waitFor(() => {
      expect(
        winnerButton(screen.getByRole("row", { name: /Beta Marine/ })).hasAttribute("disabled"),
      ).toBe(true);
    });
    expect(api.selectWinner).toHaveBeenCalledTimes(1);
    release();
    await screen.findByText("Winner selected");
  });

  it("[B4-R12] expired and declined offers cannot be selected", async () => {
    setup(compareApi(partialAndExpired));
    for (const name of ["Echo Fuels", "Foxtrot Supply"]) {
      expect(winnerButton(await row(name)).hasAttribute("disabled")).toBe(true);
    }
    expect(winnerButton(await row("Foxtrot Supply")).getAttribute("title")).toBe(
      "RFQ was declined",
    );
    expect(winnerButton(await row("Echo Fuels")).getAttribute("title")).toBe("Offer has expired");
    expect(winnerButton(await row("Alpha Marine")).hasAttribute("disabled")).toBe(false);
  });

  it("[B4-R12] the decision is shown, with the selected row marked and not selectable again", async () => {
    setup(compareApi(decided, offersInquiry({ status: "winner_selected" })));
    expect(
      await screen.findByText(/at USD 390,722.50, selected by Bea Buyer on 06 Nov 10:30 UTC/),
    ).toBeTruthy();
    expect(screen.getByText("Reason: Reliability. Known barge operator at this port")).toBeTruthy();
    const beta = await row("Beta Marine");
    expect(within(beta).getByText("Selected")).toBeTruthy();
    expect(within(beta).queryByRole("button", { name: "Select winner" })).toBeNull();
    // Another offer can still replace the winner.
    expect(winnerButton(await row("Gamma Bunkers"))).toBeTruthy();
  });

  it("[B4-R12] a decision without a reason says the lowest offer was selected", async () => {
    const data = structuredClone(decided);
    data.decision = { ...data.decision!, winner_offer_id: "oa", reason: null, note: null };
    setup(compareApi(data));
    expect(await screen.findByText("Selected as the lowest offer")).toBeTruthy();
  });

  it("[B4-R12] a viewer reads everything and has no way to select", async () => {
    setup(compareApi(decided, offersInquiry({ status: "winner_selected" })), ["viewer"]);
    expect(await screen.findByText("Decision")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Select winner" })).toBeNull();
    expect(screen.queryByRole("columnheader", { name: "Action" })).toBeNull();
    await userEvent.click(await row("Gamma Bunkers"));
    expect(screen.getByRole("complementary", { name: "Offer from Gamma Bunkers" })).toBeTruthy();
  });

  it("[B4-R12] nothing can be selected once the inquiry is nominated", async () => {
    setup(compareApi(decided, offersInquiry({ status: "nominated" })));
    await row("Alpha Marine");
    expect(screen.queryByRole("button", { name: "Select winner" })).toBeNull();
  });

  it("[B4-R12] an Operator sees a locked note and nothing is requested", () => {
    const api = compareApi(completeOnly);
    const spy = vi.spyOn(api, "getComparison");
    setup(api, ["operator"]);
    expect(screen.getByText("Hidden for your role: offer comparison")).toBeTruthy();
    expect(spy).not.toHaveBeenCalled();
  });

  it("[B4-R12] no offers show an empty table and a failed load an error state", async () => {
    setup(compareApi({ rows: [], decision: null }));
    expect(await screen.findByText("No offers yet")).toBeTruthy();
    cleanup();
    const api = {
      ...compareApi(completeOnly),
      getComparison: () => Promise.reject(new ApiError(500)),
    };
    setup(api);
    expect(await screen.findByText("Could not load the offers")).toBeTruthy();
  });

  it("[B4-R12] closing the panel or cancelling the form leaves the selection alone", async () => {
    const api = { ...compareApi(completeOnly), selectWinner: select() };
    setup(api);
    await userEvent.click(winnerButton(await row("Beta Marine")));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("form", { name: "Selection rationale" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("complementary")).toBeNull();
    expect(api.selectWinner).not.toHaveBeenCalled();
  });
});
