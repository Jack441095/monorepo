import { expect, test } from "@playwright/test";
import { PUBLIC_CHECKOUT_LIVE } from "../lib/commerce-config";

// The payment links are checked locally; these tests do not open a paid checkout.

test("pricing opens Stripe links only after the public checkout gates pass", async ({ page }) => {
  const response = await page.goto("/pricing");
  expect(response?.status()).toBe(200);
  const submit = page.getByRole("link", { name: "Buy now — £2", exact: true });
  const slo = page.getByRole("link", { name: "Buy now — £9", exact: true });
  if (PUBLIC_CHECKOUT_LIVE) {
    await expect(submit).toHaveAttribute("href", /^https:\/\/buy\.stripe\.com\//);
    await expect(slo).toHaveAttribute("href", /^https:\/\/buy\.stripe\.com\//);
    await expect(page.getByText("Secure checkout processed by Stripe.", { exact: false })).toBeVisible();
    await expect(page.getByText("NITE Submit is available as a £2", { exact: false })).toBeVisible();
  } else {
    await expect(page.locator('a[href^="https://buy.stripe.com/"]')).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Request beta access", exact: true })).toBeVisible();
    await expect(page.getByText("Paid checkout opens after release validation", { exact: false })).toBeVisible();
  }
});

for (const path of ["/products/submit", "/products/smart-sample-manager"]) {
  test(`product page respects the public checkout gate: ${path}`, async ({ page }) => {
    await page.goto(path);
    const links = page.locator('a[href^="https://buy.stripe.com/"]');
    await expect(links).toHaveCount(PUBLIC_CHECKOUT_LIVE ? 1 : 0);
    if (!PUBLIC_CHECKOUT_LIVE) await expect(page.locator('a[href="#join-waitlist"]')).toBeVisible();
  });
}

test("account page handles a purchase=pending param while signed out gracefully", async ({ page }) => {
  const response = await page.goto("/account?purchase=pending");
  expect(response?.status()).toBe(200);
  // Signed out takes priority -- shows the sign-in form, not a broken
  // "confirming your purchase" state with no user to confirm it for.
  await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();
});

test("account page with a malformed purchase param does not crash", async ({ page }) => {
  const response = await page.goto("/account?purchase=garbage");
  expect(response?.status()).toBe(200);
  await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();
});
