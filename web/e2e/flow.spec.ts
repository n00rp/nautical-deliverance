import { expect, test, type Browser, type Locator, type Page } from "@playwright/test";

// B6-R08. Environment: ND_E2E_BASE_URL (default http://localhost:8080), ND_E2E_USER and
// ND_E2E_PASSWORD (a bunker_buyer whose password is already permanent), and optionally
// ND_E2E_OPERATOR_USER / ND_E2E_OPERATOR_PASSWORD for the Operator check.
const env = (name: string) => process.env[name] ?? "";
const BUYER = { user: env("ND_E2E_USER"), password: env("ND_E2E_PASSWORD") };
const OPERATOR = { user: env("ND_E2E_OPERATOR_USER"), password: env("ND_E2E_OPERATOR_PASSWORD") };
const PREFIX = "E2E-";
const DAY_MS = 86_400_000;
/** The value of a datetime-local input (UTC) for now + days. */
const inDays = (d: number) => new Date(Date.now() + d * DAY_MS).toISOString().slice(0, 16);

type Creds = typeof BUYER;

async function signIn(page: Page, who: Creds) {
  await page.goto("/");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByLabel("Username or email").fill(who.user);
  await page.getByLabel("Password", { exact: true }).fill(who.password);
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page.getByRole("link", { name: "Inquiries" })).toBeVisible();
}

/** Opens a Radix select by its label and picks an option by name (or the first one). */
async function pick(scope: Page | Locator, label: RegExp, option?: string) {
  await scope.getByRole("combobox", { name: label }).click();
  // The options render in a portal, outside `scope`.
  const page = "page" in scope ? scope.page() : scope;
  const options = page.getByRole("option");
  await (option ? options.filter({ hasText: option }).first() : options.first()).click();
}

/** The data rows of the RFQ table whose Status cell reads `status` (the header row is not one). */
const rfqRows = (page: Page, status: string) =>
  page.getByRole("row").filter({ has: page.getByRole("cell", { name: status, exact: true }) });

async function dashboardCount(page: Page, status: string) {
  await page.goto("/#/");
  await expect(page.getByRole("heading", { name: "Inquiries by status" })).toBeVisible();
  const tile = page
    .locator("dl > div")
    .filter({ has: page.locator("dt", { hasText: new RegExp(`^${status}$`) }) });
  const count = tile.locator("dd");
  await expect(count).toHaveText(/^\d+$/);
  return Number(await count.innerText());
}

test.describe("[B6-R08] pilot 1 purchase flow", () => {
  test.skip(!BUYER.user || !BUYER.password, "ND_E2E_USER and ND_E2E_PASSWORD are not set");

  // Review Focus #5: runs even when the test aborted halfway, and cancels every E2E inquiry.
  test.afterAll(async ({ browser }, info) => {
    await cancelLeftovers(browser, String(info.project.use.baseURL));
  });

  test("[B6-R08] buyer buys, operator sees no money", async ({ page, browser }) => {
    const voyage = `${PREFIX}${String(Date.now())}`;
    await signIn(page, BUYER);
    const nominatedBefore = await dashboardCount(page, "Nominated");

    await test.step("create the inquiry with 2 lines", async () => {
      await page.goto("/#/inquiries");
      await page.getByRole("button", { name: "New inquiry" }).click();
      await pick(page, /^Vessel/);
      await page.getByRole("textbox", { name: "Voyage" }).fill(voyage);
      // The seeded vessels have no default operator, so one is chosen.
      await pick(page, /^Operator/);
      await pick(page, /^Port/, "Rotterdam");
      await page.getByLabel(/^ETA/).fill(inDays(10));
      await page.getByLabel(/^ETD/).fill(inDays(11));
      await pick(page, /^Bunkering reason/, "Bunkers only");
      await page.getByRole("button", { name: "Add line" }).click();
      for (const [i, product] of ["VLSFO 0.5%", "DMA 0.1%"].entries()) {
        const line = page.getByRole("group", { name: `Line ${String(i + 1)}` });
        await pick(line, /^Product/, product);
        await line.getByLabel(/^Quantity/).fill("500");
        await pick(line, /^ISO spec version/, "ISO 8217:2017");
      }
      await page.getByRole("button", { name: "Create inquiry" }).click();
      await expect(page.getByRole("heading", { level: 2, name: /^INQ-/ })).toBeVisible();
      await expect(page.getByText("Draft", { exact: true })).toBeVisible();
    });
    const inquiryUrl = page.url();

    await test.step("select suppliers (pre-selection) and create the RFQs", async () => {
      const take = page.getByRole("button", { name: "Take", exact: true });
      if (await take.isVisible()) await take.click();
      await page.getByRole("button", { name: "Select suppliers" }).click();
      const create = page.getByRole("button", { name: /^Create \d+ RFQ drafts$/ });
      await expect(create).toBeEnabled();
      expect(Number(/\d+/.exec(await create.innerText())?.[0])).toBeGreaterThanOrEqual(2);
      await create.click();
      await expect(page.getByRole("heading", { name: /— RFQs$/ })).toBeVisible();
    });

    await test.step("mark 2 RFQs sent; the mail link is checked, never followed", async () => {
      for (let n = 1; n <= 2; n++) {
        await rfqRows(page, "Draft").first().click();
        // Only the href: following a mailto link would open a real mail client.
        await expect(page.getByRole("link", { name: "Open in e-mail" })).toHaveAttribute(
          "href",
          /^mailto:/,
        );
        await page.getByRole("button", { name: "Mark sent", exact: true }).click();
        await page.getByRole("button", { name: "Confirm sent" }).click();
        await expect(rfqRows(page, "Sent")).toHaveCount(n);
      }
    });

    // The first offer entered is the cheaper one, so the second is the non-lowest.
    const suppliers: string[] = [];
    await test.step("enter 2 offers", async () => {
      for (const [i, prices] of [
        ["600", "700"],
        ["650", "750"],
      ].entries()) {
        // The two sent rows keep their order; no dependence on the "Offer received" wording.
        await rfqRows(page, "Sent").nth(i).click();
        await page.getByRole("link", { name: "Enter offer" }).click();
        const heading = page.getByRole("heading", { name: /Enter offer from / });
        await expect(heading).toBeVisible();
        suppliers.push((await heading.innerText()).replace(/^.*offer from /, ""));
        await page.getByLabel(/^VLSFO 0\.5% — 500/).fill(prices[0] ?? "");
        await page.getByLabel(/^DMA 0\.1% — 500/).fill(prices[1] ?? "");
        await page.getByLabel(/^Valid until/).fill(inDays(5));
        await page.getByRole("button", { name: "Save offer" }).click();
        await expect(page.getByRole("heading", { name: /— RFQs$/ })).toBeVisible();
      }
    });
    const [cheapest = "", chosen = ""] = suppliers;
    expect(chosen).not.toBe("");

    await test.step("select the non-lowest offer with a rationale", async () => {
      await page.goto(inquiryUrl);
      await page.getByRole("link", { name: "Compare offers" }).click();
      await expect(page.getByRole("row").filter({ hasText: cheapest })).toContainText("Lowest");
      await page
        .getByRole("row")
        .filter({ hasText: chosen })
        .getByRole("button", { name: "Select winner" })
        .click();
      await pick(page, /^Reason/, "Operational fit");
      await page.getByRole("textbox", { name: "Note" }).fill("E2E: closer barge slot");
      await page.getByRole("button", { name: "Confirm selection" }).click();
      await expect(page.getByText("Reason: Operational fit")).toBeVisible();
    });

    await test.step("create the nomination and mark it sent", async () => {
      await page.goto(inquiryUrl);
      await page.getByRole("button", { name: "Create nomination" }).click();
      await expect(page.getByRole("heading", { name: /— Nomination$/ })).toBeVisible();
      await page.getByRole("button", { name: "Mark sent", exact: true }).click();
      await page.getByRole("button", { name: "Confirm sent" }).click();
      await expect(page.getByRole("cell", { name: "v1" })).toBeVisible();
    });

    await test.step("the inquiry is Nominated and the dashboard moved", async () => {
      await page.goto(inquiryUrl);
      await expect(page.getByText("Nominated", { exact: true })).toBeVisible();
      await expect(page.getByText(`Nominated: ${chosen}`)).toBeVisible();
      // The tile counts the whole organisation, so other users may move it: only a lower bound is
      // race-free. Locally nobody else runs, so the run's own nomination must have raised it; on a
      // remote run the inquiry above is Nominated, so the count is at least 1.
      const local = /^(localhost|127\.0\.0\.1)$/.test(new URL(page.url()).hostname);
      const floor = local ? nominatedBefore + 1 : 1;
      await expect.poll(() => dashboardCount(page, "Nominated")).toBeGreaterThanOrEqual(floor);
    });

    await test.step("the operator sees the supplier and no USD", async () => {
      test.skip(!OPERATOR.user, "ND_E2E_OPERATOR_USER is not set");
      const context = await browser.newContext();
      try {
        const op = await context.newPage();
        await signIn(op, OPERATOR);
        await op.goto(inquiryUrl);
        await expect(op.getByText(`Nominated: ${chosen}`)).toBeVisible();
        await expect(op.locator("body")).not.toContainText("USD");
        await op.goto("/#/");
        await expect(op.getByRole("heading", { name: "Inquiries by status" })).toBeVisible();
        await expect(op.locator("body")).not.toContainText("USD");
      } finally {
        await context.close();
      }
    });
  });
});

type Listed = { id: string };
type Detail = { id: string; version: number; voyage: string | null; status: string };

/** Signs in as the buyer and cancels every non-cancelled inquiry whose voyage starts with E2E-. */
async function cancelLeftovers(browser: Browser, baseURL: string) {
  const context = await browser.newContext({ baseURL });
  try {
    await signIn(await context.newPage(), BUYER);
    // The token oidc-client-ts keeps for the app; the pilot realm needs no direct grant.
    const token = await context.pages()[0]?.evaluate(() => {
      const key = Object.keys(sessionStorage).find((k) => k.startsWith("oidc.user:"));
      const raw = key ? sessionStorage.getItem(key) : null;
      return raw ? (JSON.parse(raw) as { access_token: string }).access_token : "";
    });
    expect(token).toBeTruthy();
    const headers = { Authorization: `Bearer ${token ?? ""}` };
    const api = context.request;
    const get = async <T>(path: string) => (await (await api.get(path, { headers })).json()) as T;
    // The list (all but cancelled) has no voyage and its `q` does not search it, so the details are
    // read, ten at a time. ponytail: N detail reads; add a voyage filter to the list if it grows.
    const rows = await get<Listed[]>("/api/v1/inquiries");
    const details: Detail[] = [];
    for (let i = 0; i < rows.length; i += 10) {
      const chunk = rows.slice(i, i + 10);
      details.push(
        ...(await Promise.all(chunk.map((r) => get<Detail>(`/api/v1/inquiries/${r.id}`)))),
      );
    }
    for (const d of details) {
      if (!d.voyage?.startsWith(PREFIX) || d.status === "cancelled") continue;
      const res = await api.post(`/api/v1/inquiries/${d.id}/cancel`, {
        headers,
        data: { version: d.version, reason: "E2E cleanup" },
      });
      expect(res.ok(), `cancel ${d.id}: ${String(res.status())}`).toBe(true);
    }
  } finally {
    await context.close();
  }
}
