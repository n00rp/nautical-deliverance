import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

type Entry = { id: string; type: string };
const index = JSON.parse(readFileSync("storybook-static/index.json", "utf8")) as {
  entries: Record<string, Entry>;
};
const stories = Object.values(index.entries).filter((e) => e.type === "story");

const open = async (page: import("@playwright/test").Page, id: string) => {
  await page.goto(`/iframe.html?id=${id}&viewMode=story`);
  await page.locator("#storybook-root > *").first().waitFor();
  await page.evaluate(() => document.fonts.ready);
};

test("[B1-R13] storybook has stories", () => {
  expect(stories.length).toBeGreaterThan(0);
});

for (const scheme of ["light", "dark"] as const) {
  for (const { id } of stories) {
    test(`[B1-R13] ${id} ${scheme}: screenshot and axe`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await open(page, id);
      await expect(page).toHaveScreenshot(`${id}-${scheme}.png`);
      const { violations } = await new AxeBuilder({ page })
        // Page-level rules do not apply to an isolated component story.
        .disableRules(["page-has-heading-one", "landmark-one-main", "region"])
        .analyze();
      expect(violations, JSON.stringify(violations, null, 1)).toEqual([]);
    });
  }
}

test("[B1-R13] reduced motion disables transitions", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await open(page, "ui-button--primary");
  const duration = await page
    .getByRole("button")
    .evaluate((el) => getComputedStyle(el).transitionDuration);
  expect(duration).toBe("0s");
  await page.emulateMedia({ reducedMotion: "no-preference" });
  const normal = await page
    .getByRole("button")
    .evaluate((el) => getComputedStyle(el).transitionDuration);
  expect(normal).not.toBe("0s");
});
