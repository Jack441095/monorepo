import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

const guard = resolve("scripts/check-production-config.mjs");

function checkBuild(env: Record<string, string>) {
  // An isolated environment keeps developer/provider secrets out of failures.
  return spawnSync(process.execPath, [guard], {
    // Next's ProcessEnv type requires NODE_ENV; individual cases override it
    // without inheriting the caller's production settings or credentials.
    env: { NODE_ENV: "test", ...env },
    encoding: "utf8",
  });
}

test("Vercel production rejects a missing API even without the explicit build flag", () => {
  // The former host detector skipped every Vercel production deployment.
  const result = checkBuild({ VERCEL_ENV: "production" });
  expect(result.status).toBe(1);
  expect(result.stderr).toContain("NEXT_PUBLIC_NITE_DSP_API_URL is not set");
});

test("production rejects a local API and reports all missing sales approvals", () => {
  const result = checkBuild({
    NITEDSP_BUILD_ENV: "production",
    NEXT_PUBLIC_NITE_DSP_API_URL: "http://127.0.0.1:8420",
    NEXT_PUBLIC_CHECKOUT_LIVE: "1",
  });
  expect(result.status).toBe(1);
  expect(result.stderr).toContain("local dev endpoint");
  expect(result.stderr).toContain("NEXT_PUBLIC_STRIPE_MODE=live");
  expect(result.stderr).toContain("NEXT_PUBLIC_LEGAL_REVIEW_APPROVED=1");
  expect(result.stderr).toContain("NEXT_PUBLIC_RELEASE_READY=1");
});

test("Vercel production accepts closed checkout with a deployed API", () => {
  const result = checkBuild({
    VERCEL_ENV: "production",
    NEXT_PUBLIC_NITE_DSP_API_URL: "https://api.example.test",
  });
  expect(result.status).toBe(0);
  expect(result.stdout).toContain("VERCEL_ENV=production");
});

test("live checkout accepts the full production approval contract", () => {
  const result = checkBuild({
    VERCEL_ENV: "production",
    NEXT_PUBLIC_NITE_DSP_API_URL: "https://api.example.test",
    NEXT_PUBLIC_CHECKOUT_LIVE: "1",
    NEXT_PUBLIC_STRIPE_MODE: "live",
    NEXT_PUBLIC_LEGAL_REVIEW_APPROVED: "1",
    NEXT_PUBLIC_RELEASE_READY: "1",
    NEXT_PUBLIC_STRIPE_SUBMIT_LINK: "https://buy.stripe.com/submit-live-link",
    NEXT_PUBLIC_STRIPE_SLO_LINK: "https://buy.stripe.com/slo-live-link",
  });
  expect(result.status).toBe(0);
});

test("live checkout rejects missing or non-Stripe payment links", () => {
  const result = checkBuild({
    VERCEL_ENV: "production",
    NEXT_PUBLIC_NITE_DSP_API_URL: "https://api.example.test",
    NEXT_PUBLIC_CHECKOUT_LIVE: "1",
    NEXT_PUBLIC_STRIPE_MODE: "live",
    NEXT_PUBLIC_LEGAL_REVIEW_APPROVED: "1",
    NEXT_PUBLIC_RELEASE_READY: "1",
    NEXT_PUBLIC_STRIPE_SUBMIT_LINK: "https://buy.stripe.com",
  });
  expect(result.status).toBe(1);
  expect(result.stderr).toContain("NEXT_PUBLIC_STRIPE_SUBMIT_LINK must be an HTTPS Stripe-hosted checkout URL");
  expect(result.stderr).toContain("NEXT_PUBLIC_STRIPE_SLO_LINK must be an HTTPS Stripe-hosted checkout URL");
});

for (const vercelEnv of ["", "preview"]) {
  test(`local Next.js builds and ${vercelEnv || "unset"} Vercel environments stay isolated`, () => {
    // Next.js uses production NODE_ENV for local builds as well as releases.
    const result = checkBuild({ NODE_ENV: "production", VERCEL_ENV: vercelEnv });
    expect(result.status).toBe(0);
    expect(result.stdout).toBe("");
  });
}
