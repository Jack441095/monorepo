#!/usr/bin/env node
/**
 * Release-time guard — Phase 5.5, Section 9.
 *
 * `npm run build` alone (used for local/staging builds throughout this
 * project) must keep working with the localhost default — this script is
 * only invoked by `build:production`. Mirrors the backend's
 * config.py._validate_production_config — same "fail loudly, collect
 * every problem before exiting" shape.
 *
 * Vercel production builds must engage the guard even when the explicit
 * flag is missing. NODE_ENV cannot distinguish a local Next.js build from
 * a deployed one, and Vercel previews need their own isolated API settings.
 */
const isExplicitProductionBuild = process.env.NITEDSP_BUILD_ENV === "production";
const isVercelProductionBuild = process.env.VERCEL_ENV === "production";

if (!isExplicitProductionBuild && !isVercelProductionBuild) {
  // Local builds and previews do not carry the production launch contract.
  process.exit(0);
}

const reason = isExplicitProductionBuild
  ? "NITEDSP_BUILD_ENV=production"
  : "VERCEL_ENV=production";
console.log(`Checking deploy configuration (${reason}).`);

// Fatal: these break core functionality if wrong.
const problems = [];
// Non-fatal: these degrade a single surface, so they are reported loudly
// but never block a release.
const warnings = [];

const apiUrl = process.env.NEXT_PUBLIC_NITE_DSP_API_URL ?? "";
if (!apiUrl) {
  problems.push("NEXT_PUBLIC_NITE_DSP_API_URL is not set");
} else if (/localhost|127\.0\.0\.1|:8420|:3000/.test(apiUrl)) {
  problems.push(`NEXT_PUBLIC_NITE_DSP_API_URL=${JSON.stringify(apiUrl)} still points at a local dev endpoint`);
}

if (process.env.NEXT_PUBLIC_CHECKOUT_LIVE === "1") {
  if (process.env.NEXT_PUBLIC_STRIPE_MODE !== "live") {
    problems.push("NEXT_PUBLIC_CHECKOUT_LIVE=1 requires NEXT_PUBLIC_STRIPE_MODE=live");
  }
  if (process.env.NEXT_PUBLIC_LEGAL_REVIEW_APPROVED !== "1") {
    problems.push("live checkout requires NEXT_PUBLIC_LEGAL_REVIEW_APPROVED=1");
  }
  if (process.env.NEXT_PUBLIC_RELEASE_READY !== "1") {
    problems.push("live checkout requires NEXT_PUBLIC_RELEASE_READY=1");
  }
  for (const name of ["NEXT_PUBLIC_STRIPE_SUBMIT_LINK", "NEXT_PUBLIC_STRIPE_SLO_LINK"]) {
    const value = process.env[name] ?? "";
    let isHostedStripeUrl = false;
    try {
      const url = new URL(value);
      isHostedStripeUrl =
        url.protocol === "https:" &&
        url.pathname !== "/" &&
        (url.hostname === "buy.stripe.com" || url.hostname === "checkout.stripe.com");
    } catch {
      // An absent or malformed public link keeps checkout closed.
    }
    if (!isHostedStripeUrl) {
      problems.push(`${name} must be an HTTPS Stripe-hosted checkout URL`);
    }
  }
}

// proxy.ts fails closed: with no password configured, /portfolio serves 403
// to everyone rather than unlocking. That is the safe failure, but it is a
// silent one, so surface it at build time instead of on first visit.
if (!process.env.PORTFOLIO_PASSWORD) {
  warnings.push("PORTFOLIO_PASSWORD is not set — /portfolio will return 403 for every visitor");
}

for (const w of warnings) console.warn(`  warning: ${w}`);

if (problems.length > 0) {
  console.error("Refusing a production build with invalid configuration:");
  for (const p of problems) console.error(`  - ${p}`);
  process.exit(1);
}

console.log("OK: deploy configuration checked, no local dev endpoints found.");
