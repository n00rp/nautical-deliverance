import type { Meta, StoryObj } from "@storybook/react-vite";
import type { Role } from "../ui/RoleGate/RoleGate";
import { ToastHost, ToastProvider } from "../ui/Toast/Toast";
import { OfferEntry } from "./OfferEntry";
import { entryApi, m3Lines, mtLines, savedOffer } from "./testSupport";

const story = (api: ReturnType<typeof entryApi>, roles: Role[]): StoryObj => ({
  render: () => (
    <ToastProvider>
      <OfferEntry inquiryId="i1" rfqId="r1" api={api} roles={roles} />
      <ToastHost />
    </ToastProvider>
  ),
});

export default {
  title: "Offers/OfferEntry",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

/** An empty form: an mt line, an m3 line that asks for a density and one that does not. */
export const NewOffer = story(entryApi(m3Lines), ["bunker_buyer"]);
/** A saved, complete offer with its live total. */
export const EditOffer = story(entryApi(mtLines, savedOffer), ["admin"]);
export const AsOperator = story(entryApi(mtLines), ["operator"]);
