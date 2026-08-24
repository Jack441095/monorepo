// Visual review capture — static screenshots at required breakpoints.
// Usage: node scripts/capture-visual-review.mjs [baseURL]
// Requires a server already running (e.g. npm run start -- -p 3100).
// Output: docs/motion-review/<route>-<width>.jpg

import { chromium } from "playwright-core";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const BASE = process.argv[2] ?? "http://127.0.0.1:3100";
const OUT_DIR = join(process.cwd(), "docs", "motion-review");
const WIDTHS = [1440, 768, 390];
const ROUTES = [
  ["home", "/"],
  ["slo", "/products/smart-sample-manager"],
  ["products", "/products"],
];

mkdirSync(OUT_DIR, { recursive: true });

const browser = await chromium.launch();
for (const width of WIDTHS) {
  const context = await browser.newContext({
    viewport: { width, height: Math.round(width * 0.66) },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  for (const [name, route] of ROUTES) {
    await page.goto(`${BASE}${route}`, { waitUntil: "networkidle" });
    // Let reveals settle: kill smooth scrolling, sweep the page so every
    // IntersectionObserver fires, return to top, allow transitions to finish.
    await page.evaluate(async () => {
      document.documentElement.style.scrollBehavior = "auto";
      const step = window.innerHeight / 2;
      for (let y = 0; y <= document.body.scrollHeight; y += step) {
        window.scrollTo(0, y);
        await new Promise((r) => setTimeout(r, 160));
      }
      window.scrollTo(0, 0);
    });
    await page.waitForTimeout(1100);
    const file = join(OUT_DIR, `${name}-${width}.jpg`);
    await page.screenshot({ path: file, type: "jpeg", quality: 82, fullPage: true });
    console.log("captured", file);
  }
  await context.close();
}
await browser.close();
