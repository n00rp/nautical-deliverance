import { expect, it } from "vitest";
import { userManager } from "./auth";

it("[S0-R03] userManager uses authorization code flow with the configured client", () => {
  expect(userManager.settings.authority).toBe("http://idp.test/realms/x");
  expect(userManager.settings.client_id).toBe("nd-web");
  expect(userManager.settings.response_type).toBe("code");
});
