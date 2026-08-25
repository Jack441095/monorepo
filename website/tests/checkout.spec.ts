import { expect, test } from "@playwright/test";

// Updated for WEBSITE COMMERCIAL EXPERIENCE V1 to match the live pricing
// model (£2.99 perpetual planned, free closed beta, checkout not yet open).
// Frontend-only boundary tests. Deliberately do NOT attempt to drive a real
// magic-link sign-in or Paddle's third-party checkout iframe here -- that's
// exactly the kind of third-party-dependent flow that makes e2e suites
// brittle.

test("pricing page renders normally with no checkout-related errors", async ({ page }) => {
  const response = await page.goto("/pricing");
  expect(response?.status()).toBe(200);
  await expect(page.getByText("Perpetual Licence — planned")).toBeVisible();
  await expect(page.getByText("£2.99", { exact: true })).toBeVisible();
  // No leaked error state on an ordinary visit.
  await expect(page.getByText(/something went wrong/i)).not.toBeVisible();
});

test("pricing page offers a primary action that matches commercial maturity", async ({ page }) => {
  // Checkout is not open yet, so the honest primary action is a beta
  // request -- never a dead Buy button.
  await page.goto("/pricing");
  const betaLink = page.getByRole("link", { name: /request beta access/i });
  await expect(betaLink).toBeVisible();
});

test("pricing page exposes the correctly labelled checkout action only when enabled", async ({ page }) => {
  await page.goto("/pricing");
  if (process.env.NEXT_PUBLIC_CHECKOUT_LIVE === "1") {
    const expectedLabel = process.env.NEXT_PUBLIC_PADDLE_ENV === "sandbox"
      ? "Test Checkout (Sandbox)"
      : "Buy now";
    await expect(page.getByRole("button", { name: expectedLabel })).toBeVisible();
  } else {
    await expect(page.getByRole("link", { name: /request beta access/i })).toBeVisible();
  }
});

test("beta request CTA routes visitors into the request journey, not a dead end", async ({ page }) => {
  await page.goto("/pricing");
  await page.getByRole("link", { name: /request beta access/i }).click();
  await expect(page).toHaveURL(/\/beta/);
  await expect(page.getByRole("heading", { name: "Try NITE software early." })).toBeVisible();
});

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
