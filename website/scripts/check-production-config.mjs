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
 * Engagement rule. Originally this keyed solely off an explicit
 * NITEDSP_BUILD_ENV=production flag, deliberately NOT off Next.js's own
 * NODE_ENV (which `next build` sets to "production" even for a local
 * build). That left one hole: if a real deploy simply never set the flag,
 * the guard exited 0 and the deploy shipped whatever was configured --
 * including a site pointing at localhost. So a detected Railway build now
 * engages the guard too. A correctly configured deploy is unaffected; only
 * a deploy that is already broken starts failing, which is the point of a
 * fail-closed check.
 */
const isExplicitProductionBuild = process.env.NITEDSP_BUILD_ENV === "production";
// Railway injects these into every build; presence means "this is a real
// deploy", not someone's laptop.
const isRailwayBuild = Boolean(
  process.env.RAILWAY_ENVIRONMENT ||
    process.env.RAILWAY_SERVICE_ID ||
    process.env.RAILWAY_PROJECT_ID,
);

if (!isExplicitProductionBuild && !isRailwayBuild) {
  process.exit(0);
}

const reason = isExplicitProductionBuild
  ? "NITEDSP_BUILD_ENV=production"
  : "a Railway deploy build was detected";
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
  if (process.env.NEXT_PUBLIC_PADDLE_ENV !== "production") {
    problems.push("NEXT_PUBLIC_CHECKOUT_LIVE=1 requires NEXT_PUBLIC_PADDLE_ENV=production");
  }
  if (process.env.NEXT_PUBLIC_LEGAL_REVIEW_APPROVED !== "1") {
    problems.push("live checkout requires NEXT_PUBLIC_LEGAL_REVIEW_APPROVED=1");
  }
  if (process.env.NEXT_PUBLIC_RELEASE_READY !== "1") {
    problems.push("live checkout requires NEXT_PUBLIC_RELEASE_READY=1");
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
