import { expect, test } from "@playwright/test";

// Frontend-only boundary tests. Deliberately do NOT attempt to drive a real
// magic-link sign-in or Paddle's third-party checkout iframe here -- that's
// exactly the kind of third-party-dependent flow that makes e2e suites
// brittle. Real provider validation (real auth, real checkout creation,
// real Paddle sandbox transactions) was done separately via direct API
// calls against the deployed backend -- see docs/PADDLE_INTEGRATION_AUDIT.md.
// These tests only assert what the frontend does deterministically, on its
// own, regardless of whether a Paddle client token happens to be configured
// in the environment these run against.

test("pricing page renders normally with no checkout-related errors", async ({ page }) => {
  const response = await page.goto("/pricing");
  expect(response?.status()).toBe(200);
  await expect(page.getByText("£10", { exact: true })).toBeVisible();
  // No leaked error state on an ordinary visit.
  await expect(page.getByText(/something went wrong/i)).not.toBeVisible();
});

test("pricing page has exactly one primary action, Buy or Sign in", async ({ page }) => {
  await page.goto("/pricing");
  const buyButton = page.getByRole("button", { name: /buy smart sample manager/i });
  const signInLink = page.getByRole("link", { name: /^sign in$/i });
  // Exactly one of the two states is live at any given environment
  // configuration -- Buy once a Paddle client token exists, Sign in (the
  // "checkout is not yet live" fallback) until it does.
  const buyVisible = await buyButton.isVisible().catch(() => false);
  const signInVisible = await signInLink.isVisible().catch(() => false);
  expect(buyVisible !== signInVisible).toBe(true);
});

test("unauthenticated visitor is routed toward sign-in, not a dead end", async ({ page }) => {
  await page.goto("/pricing");
  const buyButton = page.getByRole("button", { name: /buy smart sample manager/i });
  const signInLink = page.getByRole("link", { name: /^sign in$/i });

  if (await signInLink.isVisible().catch(() => false)) {
    await signInLink.click();
  } else {
    await buyButton.click();
  }
  await expect(page).toHaveURL(/\/account/);
  // Either the sign-in form or a loading state -- never a raw error.
  await expect(page.getByText(/something went wrong/i)).not.toBeVisible();
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
