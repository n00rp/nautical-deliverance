import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { parseInquiries, useHash } from "../admin/routes";
import { InquiryPage } from "../inquiries/InquiryPage";
import { inquiry, inquiryApi, master } from "../inquiries/pageSupport";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { Nomination } from "./Nomination";
import { nominationApi } from "./testSupport";

afterEach(() => {
  cleanup();
  window.location.hash = "";
});

/** `userEvent` behind a proxy that counts every call, so no step can go uncounted (B4 lesson). */
function counted() {
  let calls = 0;
  const user = new Proxy(userEvent, {
    get(target, key) {
      const value: unknown = Reflect.get(target, key);
      if (typeof value !== "function") return value;
      return (...args: unknown[]) => {
        calls += 1;
        return (value as (...a: unknown[]) => unknown)(...args);
      };
    },
  });
  return { user, calls: () => calls };
}

describe("step budget", () => {
  it("[B5-R11] creating a nomination and marking it sent from the inquiry page takes 3 interactions", async () => {
    const noms = nominationApi([], "winner_selected");
    const sent = vi.spyOn(noms, "markNominationSent");
    const page = {
      ...inquiryApi(inquiry({ status: "winner_selected" })),
      createNomination: noms.createNomination,
    };
    function Routes() {
      const route = parseInquiries(useHash());
      return route?.view === "nomination" ? (
        <Nomination inquiryId="i1" api={noms} roles={["bunker_buyer"]} />
      ) : (
        <InquiryPage id="i1" api={page} master={master} roles={["bunker_buyer"]} />
      );
    }
    window.location.hash = "#/inquiries/i1";
    render(
      <ToastProvider>
        <Routes />
        <ToastHost />
      </ToastProvider>,
    );

    const { user, calls } = counted();
    await user.click(await screen.findByRole("button", { name: "Create nomination" }));
    await user.click(await screen.findByRole("button", { name: "Mark sent" }));
    await user.click(await screen.findByRole("button", { name: "Confirm sent" }));

    await waitFor(() => {
      expect(sent).toHaveBeenCalledTimes(1);
    });
    // Documented count: Create nomination (1), Mark sent (2), Confirm sent (3).
    expect(calls()).toBe(3);
    expect(window.location.hash).toBe("#/inquiries/i1/nomination");
  });
});
