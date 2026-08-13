#!/usr/bin/env node
/**
 * Release-time guard -- Phase 5.5, Section 9.
 *
 * `npm run build` alone (used for local/staging builds throughout this
 * project) must keep working with the localhost default -- this script is
 * only invoked by `build:production`, gated on an explicit
 * NITEDSP_BUILD_ENV=production flag (never inferred from Next.js's own
 * NODE_ENV, which `next build` sets to "production" for optimization
 * purposes even for a local build). Mirrors the backend's
 * config.py._validate_production_config -- same "fail loudly, collect
 * every problem before exiting" shape.
 */
if (process.env.NITEDSP_BUILD_ENV !== "production") {
  process.exit(0);
}

const problems = [];
const apiUrl = process.env.NEXT_PUBLIC_NITE_DSP_API_URL ?? "";

if (!apiUrl) {
  problems.push("NEXT_PUBLIC_NITE_DSP_API_URL is not set");
} else if (/localhost|127\.0\.0\.1|:8420|:3000/.test(apiUrl)) {
  problems.push(`NEXT_PUBLIC_NITE_DSP_API_URL=${JSON.stringify(apiUrl)} still points at a local dev endpoint`);
}

if (problems.length > 0) {
  console.error("Refusing a production build with invalid configuration:");
  for (const p of problems) console.error(`  - ${p}`);
  process.exit(1);
}

console.log("OK: production build configuration checked, no local dev endpoints found.");
