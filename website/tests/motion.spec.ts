import { expect, test } from "@playwright/test";

/* Interaction-layer regression coverage.
   Deliberately never asserts exact animation coordinates — only behaviour
   contracts: clicks still land, content stays visible, state is conveyed
   accessibly, and nothing overflows. */

test("magnetic CTA retains normal click navigation while engaged", async ({ page }) => {
  await page.goto("/");
  const cta = page.getByRole("link", { name: "Explore the products" });
  await cta.hover();
  // Drift across the control while magnetically engaged; the hit area must
  // remain stationary, so the click still lands.
  await page.mouse.move(700, 400);
  await cta.click();
  await expect(page).toHaveURL(/\/products/);
});

test("demo completes an illustrative scan and keeps its disclosure", async ({ page }) => {
  await page.goto("/");
  await page.getByText("DSP SIGNAL CLASSIFIER").scrollIntoViewIfNeeded();
  await page.getByRole("button", { name: "take_new_001.wav" }).click();
  await expect(page.getByText("SNARE", { exact: true })).toBeVisible({ timeout: 5000 });
  await expect(page.getByText(/Illustrative workflow simulation/i)).toBeVisible();
  // Scoped to the SLO demo: the homepage now shows two demos (Submit + SLO),
  // each with its own honest SIMULATION chip.
  const sloDemo = page.getByLabel("SLO sample analysis");
  await expect(sloDemo.getByText("SIMULATION", { exact: true })).toBeVisible();
});

test("reduced motion: reveals never hide content and CTA still works", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  const revealedHeading = page.getByRole("heading", { name: /Real-time timbral signature extraction/i });
  await revealedHeading.scrollIntoViewIfNeeded();
  await expect(revealedHeading).toBeVisible();
  const opacity = await revealedHeading.evaluate((el) => getComputedStyle(el).opacity);
  expect(Number(opacity)).toBeGreaterThan(0.9);

  const cta = page.getByRole("link", { name: "Explore the products" });
  await cta.click();
  await expect(page).toHaveURL(/\/products/);
});

test("touch/mobile viewport has no horizontal overflow on key routes", async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    isMobile: true,
  });
  const page = await context.newPage();
  for (const route of ["/", "/products", "/products/smart-sample-manager", "/pricing"]) {
    await page.goto(route);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, `horizontal overflow on ${route}`).toBeLessThanOrEqual(1);
  }
  await context.close();
});

test("nav indicator aligns with the active route and conveys state accessibly", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/pricing");
  // Scoped to the primary nav — the footer legitimately repeats these links.
  const nav = page.getByLabel("Primary");
  const pricingLink = nav.getByRole("link", { name: "Pricing" });
  await expect(pricingLink).toHaveAttribute("aria-current", "page");

  const indicator = page.locator(".nav-indicator");
  const linkBox = await pricingLink.boundingBox();
  await expect
    .poll(async () => {
      const box = await indicator.boundingBox();
      if (!box || box.width === 0) return false;
      const linkCenter = linkBox!.x + linkBox!.width / 2;
      const indicatorCenter = box.x + box.width / 2;
      return Math.abs(linkCenter - indicatorCenter) < 8;
    }, { timeout: 3000 })
    .toBe(true);
});

test("high-interaction routes load without console or page errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(String(err)));
  for (const route of ["/", "/products", "/products/smart-sample-manager"]) {
    await page.goto(route);
    await page.waitForTimeout(400);
  }
  expect(errors).toEqual([]);
});
