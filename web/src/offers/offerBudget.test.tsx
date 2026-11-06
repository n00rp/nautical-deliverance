import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { OfferApi } from "../offerApi";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { OfferEntry } from "./OfferEntry";
import { entryApi, mtLines, savedOffer } from "./testSupport";

afterEach(() => {
  cleanup();
  window.location.hash = "";
});

describe("step budget", () => {
  it("[B4-R12] entering an offer with 2 lines, 2 fixed costs and valid until takes at most 15 interactions", async () => {
    const createOffer = vi.fn<OfferApi["createOffer"]>().mockResolvedValue(savedOffer);
    render(
      <ToastProvider>
        <OfferEntry
          inquiryId="i1"
          rfqId="r1"
          api={{ ...entryApi(mtLines), createOffer }}
          roles={["bunker_buyer"]}
        />
        <ToastHost />
      </ToastProvider>,
    );

    let steps = 0;
    const type = async (label: string, text: string) => {
      steps += 1;
      await userEvent.type(await screen.findByLabelText(label), text);
    };
    await type("VLSFO 0.5% — 500 mt", "612.345");
    await type("MGO 0.1% — 100 mt", "845.5");
    await type("Barging", "1200");
    await type("Port call", "350");
    steps += 1;
    fireEvent.change(screen.getByLabelText(/^Valid until/), {
      target: { value: "2026-11-10T08:00" },
    });
    steps += 1;
    await userEvent.click(screen.getByRole("button", { name: "Save offer" }));

    await waitFor(() => {
      expect(createOffer).toHaveBeenCalledTimes(1);
    });
    expect(createOffer.mock.calls[0]![1]).toMatchObject({
      valid_until: "2026-11-10T08:00:00.000Z",
      barging_cost: "1200",
      port_call_cost: "350",
      agent_cost: "0.00",
      lines: [
        { inquiry_line_id: "l1", price_per_mt: "612.345" },
        { inquiry_line_id: "l2", price_per_mt: "845.5" },
      ],
    });
    // Documented count: 2 prices (1-2), 2 fixed costs (3-4), valid until (5), Save offer (6).
    expect(steps).toBe(6);
    expect(steps).toBeLessThanOrEqual(15);
  });
});
