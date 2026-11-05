import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { readdirSync, readFileSync } from "node:fs";

type Entry = { id: string; type: string };
const index = JSON.parse(readFileSync("storybook-static/index.json", "utf8")) as {
  entries: Record<string, Entry>;
};
const stories = Object.values(index.entries).filter((e) => e.type === "story");

const open = async (page: import("@playwright/test").Page, id: string) => {
  await page.goto(`/iframe.html?id=${id}&viewMode=story`);
  await page.locator("#storybook-root > *").first().waitFor();
  await page.evaluate(async () => {
    await Promise.all(
      [
        '400 1em "IBM Plex Sans"',
        '500 1em "IBM Plex Sans"',
        '600 1em "IBM Plex Sans"',
        '600 1em "IBM Plex Sans Condensed"',
        '400 1em "IBM Plex Mono"',
        '500 1em "IBM Plex Mono"',
      ].map((f) => document.fonts.load(f)),
    );
    await document.fonts.ready;
  });
};

test("[B1-R13] no orphan baselines", () => {
  const expected = new Set(stories.flatMap(({ id }) => [`${id}-light.png`, `${id}-dark.png`]));
  const orphans = readdirSync("tests/visual/__screenshots__").filter((f) => !expected.has(f));
  expect(orphans, `orphan baselines (delete them): ${orphans.join(", ")}`).toEqual([]);
});

test("[B1-R13] storybook has stories", () => {
  expect(stories.length).toBeGreaterThan(0);
});

for (const scheme of ["light", "dark"] as const) {
  for (const { id } of stories) {
    test(`[B1-R13] ${id} ${scheme}: screenshot and axe`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await open(page, id);
      await expect(page.locator("#storybook-root")).toHaveScreenshot(`${id}-${scheme}.png`);
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

// Review Focus 2 and 4: 60+ char unbroken text never widens the page; tables scroll inside their container.
for (const id of [
  "ui-table--long-name",
  "ui-table--offer-table",
  "ui-detailpanel--beside-table",
  "ui-historylist--default",
]) {
  test(`[B1-R13] ${id}: no horizontal page overflow at 400 px`, async ({ page }) => {
    await page.setViewportSize({ width: 400, height: 800 });
    await open(page, id);
    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
  });
}

test("[B1-R13] table cells wrap long unbroken text", async ({ page }) => {
  await open(page, "ui-table--long-name");
  const wrap = await page
    .getByRole("cell")
    .first()
    .evaluate((el) => getComputedStyle(el).overflowWrap);
  expect(wrap).toBe("anywhere");
});
