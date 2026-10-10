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

test("pricing explains that a returned Stripe test session did not charge real money", async ({ page }) => {
  await page.goto("/pricing?checkout=success&session_id=cs_test_example");
  await expect(page.getByRole("status")).toContainText("No real money was charged");
  await expect(page.getByRole("status")).toContainText("does not create a production licence");
  await expect(page.getByRole("status").getByRole("link")).toHaveCount(0);
});

test("pricing sends live checkout returns to server-confirmed account status", async ({ page }) => {
  await page.goto("/pricing?checkout=success&session_id=cs_live_example");
  await expect(page.getByRole("status")).toContainText("confirm payments on the server");
  await expect(page.getByRole("status").getByRole("link", { name: "Check your account" }))
    .toHaveAttribute("href", "/account?purchase=pending");
});

for (const path of ["/products/submit", "/products/smart-sample-manager"]) {
  test(`product page respects the public checkout gate: ${path}`, async ({ page }) => {
    await page.goto(path);
    const links = page.locator('a[href^="https://buy.stripe.com/"]');
    await expect(links).toHaveCount(PUBLIC_CHECKOUT_LIVE ? 1 : 0);
    if (!PUBLIC_CHECKOUT_LIVE) await expect(page.locator('a[href="#join-waitlist"]').first()).toBeVisible();
  });
}

test("account page handles a purchase=pending param while signed out gracefully", async ({ page }) => {
  const response = await page.goto("/account?purchase=pending");
  expect(response?.status()).toBe(200);
  // Signed out takes priority -- shows the sign-in form, not a broken
  // "confirming your purchase" state with no user to confirm it for.
  await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();
});

test("account refreshes licences while a returning customer's purchase is pending", async ({ page }) => {
  const previousLicence = {
    id: "entitlement_previous",
    product_id: "nite-submit",
    license_key: "PREVIOUS-LICENCE-KEY",
    license_type: "perpetual",
    status: "active",
    expires_at: null,
  };
  const newLicence = {
    ...previousLicence,
    id: "entitlement_new",
    license_key: "NEW-LICENCE-KEY",
  };
  let entitlementReads = 0;

  await page.route("**/api/auth/me", (route) => route.fulfill({ json: {
    id: "user_existing_customer",
    email: "buyer@example.com",
    created_at: "2026-10-01T00:00:00Z",
  } }));
  await page.route("**/api/auth/entitlements", (route) => {
    entitlementReads += 1;
    return route.fulfill({ json: entitlementReads < 3 ? [previousLicence] : [previousLicence, newLicence] });
  });

  await page.goto("/account?purchase=pending");
  await expect(page.getByText("PREVIOUS-LICENCE-KEY")).toBeVisible();
  await expect(page.getByText("NEW-LICENCE-KEY")).toBeVisible({ timeout: 10_000 });
  expect(entitlementReads).toBeGreaterThanOrEqual(3);
});

test("account page with a malformed purchase param does not crash", async ({ page }) => {
  const response = await page.goto("/account?purchase=garbage");
  expect(response?.status()).toBe(200);
  await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();
});
