import { expect, test } from "@playwright/test";

const CRITICAL_ROUTES = [
  "/",
  "/products",
  "/products/smart-sample-manager",
  "/pricing",
  "/support",
  "/learn",
  "/learn/smart-sample-manager/getting-started",
  "/learn/smart-sample-manager/installation",
  "/learn/smart-sample-manager/find-similar",
  "/learn/smart-sample-manager/visual-map",
  "/learn/smart-sample-manager/ableton-integration",
  "/learn/smart-sample-manager/troubleshooting",
  "/learn/smart-sample-manager/faq",
  "/account",
  "/privacy",
  "/terms",
  "/eula",
  "/refund-policy",
];

test.describe("critical routes", () => {
  for (const route of CRITICAL_ROUTES) {
    test(`${route} returns 200`, async ({ page }) => {
      const response = await page.goto(route);
      expect(response?.status()).toBe(200);
    });
  }
});

test("homepage identifies NITE DSP and Smart Sample Manager", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByText("NITE DSP").first()).toBeVisible();
  await expect(page.getByText(/Sample Library Optimiser/i).first()).toBeVisible();
});

test("desktop nav has no visible menu button, mobile nav does", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/");
  await expect(page.getByRole("button", { name: /open menu/i })).toBeHidden();

  await page.setViewportSize({ width: 375, height: 800 });
  await page.reload();
  const menuButton = page.getByRole("button", { name: /open menu/i });
  await expect(menuButton).toBeVisible();

  // Regression test for the fixed mobile-nav gap: every nav link must be
  // reachable once the menu opens. Scoped to #mobile-nav specifically --
  // the footer also has a "Learn" link, which is a separate, legitimate
  // element, not the one this test is protecting.
  await menuButton.click();
  const mobileNav = page.locator("#mobile-nav");
  await expect(mobileNav.getByRole("link", { name: "Learn" })).toBeVisible();
  await expect(mobileNav.getByRole("link", { name: "Pricing" })).toBeVisible();
  await expect(mobileNav.getByRole("link", { name: "Support" })).toBeVisible();
});

test("public product count is exactly one, and no WIP products are named", async ({ page }) => {
  await page.goto("/");
  const bodyText = await page.textContent("body");
  for (const wip of ["KENN", "AutoMix", "AudioGen", "Thursday", "MIDI Generator"]) {
    expect(bodyText).not.toContain(wip);
  }
});

test("no production page links to localhost or a Railway subdomain", async ({ page }) => {
  await page.goto("/");
  const hrefs = await page.locator("a[href]").evaluateAll((els) =>
    els.map((el) => el.getAttribute("href") || "")
  );
  for (const href of hrefs) {
    expect(href).not.toContain("localhost");
    expect(href).not.toContain(".up.railway.app");
  }
});

test("sitemap includes the Learn hub routes", async ({ request }) => {
  const res = await request.get("/sitemap.xml");
  expect(res.status()).toBe(200);
  const body = await res.text();
  expect(body).toContain("/learn/smart-sample-manager/getting-started");
  expect(body).toContain("www.nitedsp.co.uk");
});

test("Ableton workflow is consistently labeled experimental", async ({ page }) => {
  await page.goto("/products/smart-sample-manager");
  await expect(page.getByText("Experimental", { exact: false }).first()).toBeVisible();
});
