import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { OfferApi } from "../offerApi";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { Comparison } from "./Comparison";
import { compareApi, completeOnly, offersInquiry } from "./comparisonSupport";

beforeAll(() => {
  // jsdom lacks the pointer/scroll APIs Radix Select uses.
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => undefined;
  Element.prototype.releasePointerCapture = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
});

afterEach(cleanup);

const setup = () => {
  const selectWinner = vi.fn<OfferApi["selectWinner"]>().mockResolvedValue(offersInquiry());
  render(
    <ToastProvider>
      <Comparison
        inquiryId="i1"
        api={{ ...compareApi(completeOnly), selectWinner }}
        roles={["bunker_buyer"]}
      />
      <ToastHost />
    </ToastProvider>,
  );
  return selectWinner;
};

describe("step budget", () => {
  it("[B4-R12] selecting the lowest offer takes at most 3 interactions", async () => {
    const selectWinner = setup();
    let steps = 0;
    const alpha = await screen.findByRole("row", { name: /Alpha Marine/ });
    steps += 1; // Select winner on the lowest row
    await userEvent.click(within(alpha).getByRole("button", { name: "Select winner" }));
    steps += 1; // Confirm winner
    await userEvent.click(screen.getByRole("button", { name: "Confirm winner" }));
    await waitFor(() => {
      expect(selectWinner).toHaveBeenCalledWith("i1", 4, { offer_id: "oa" });
    });
    expect(steps).toBe(2);
    expect(steps).toBeLessThanOrEqual(3);
  });

  it("[B4-R12] selecting a non-lowest offer with a rationale takes at most 6 interactions", async () => {
    const selectWinner = setup();
    let steps = 0;
    const beta = await screen.findByRole("row", { name: /Beta Marine/ });
    steps += 1; // Select winner opens the rationale form
    await userEvent.click(within(beta).getByRole("button", { name: "Select winner" }));
    steps += 1; // open the reason list
    await userEvent.click(await screen.findByRole("combobox", { name: /Reason/ }));
    steps += 1; // choose Other, which needs a note
    await userEvent.click(await screen.findByRole("option", { name: "Other" }));
    steps += 1; // write the note
    await userEvent.type(screen.getByLabelText(/Note/), "Only barge at this port");
    steps += 1; // Confirm selection
    await userEvent.click(screen.getByRole("button", { name: "Confirm selection" }));
    await waitFor(() => {
      expect(selectWinner).toHaveBeenCalledWith("i1", 4, {
        offer_id: "ob",
        reason: "other",
        note: "Only barge at this port",
      });
    });
    expect(steps).toBe(5);
    expect(steps).toBeLessThanOrEqual(6);
  });
});
