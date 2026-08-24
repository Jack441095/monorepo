// Utility-route spot-check captures (not part of required review set).
import { chromium } from "playwright-core";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const BASE = process.argv[2] ?? "http://127.0.0.1:3100";
const OUT = join(process.cwd(), "docs", "motion-review", "utility");
mkdirSync(OUT, { recursive: true });

const ROUTES = [["pricing", "/pricing"], ["support", "/support"], ["learn", "/learn"], ["account", "/account"]];
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 950 } });
const page = await context.newPage();
for (const [name, route] of ROUTES) {
  await page.goto(`${BASE}${route}`, { waitUntil: "networkidle" });
  await page.evaluate(async () => {
    document.documentElement.style.scrollBehavior = "auto";
    for (let y = 0; y <= document.body.scrollHeight; y += window.innerHeight / 2) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 120));
    }
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(800);
  await page.screenshot({ path: join(OUT, `${name}-1440.jpg`), type: "jpeg", quality: 80, fullPage: true });
  console.log("captured", name);
}
await browser.close();
