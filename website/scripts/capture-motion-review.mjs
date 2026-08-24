// Motion review recordings — short local videos of the five flagship
// interaction behaviors. Never uploaded anywhere; owner-review assets only.
// Usage: node scripts/capture-motion-review.mjs [baseURL]
// Requires a running server. Output: docs/motion-review/video/*.webm

import { chromium } from "playwright-core";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const BASE = process.argv[2] ?? "http://127.0.0.1:3100";
const OUT = join(process.cwd(), "docs", "motion-review", "video");
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();

async function record(name, scenario) {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    recordVideo: { dir: OUT, size: { width: 1280, height: 800 } },
  });
  const page = await context.newPage();
  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
  await scenario(page);
  await page.waitForTimeout(600);
  await context.close();
  const rename = await page.video()?.path();
  console.log("recorded", name, rename ?? "");
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

await record("1-hero-pointer-lighting", async (page) => {
  await sleep(400);
  for (const [x, y] of [
    [200, 200], [640, 150], [1100, 250], [1150, 500], [800, 600],
    [300, 550], [640, 350], [1000, 180],
  ]) {
    await page.mouse.move(x, y, { steps: 24 });
    await sleep(320);
  }
});

await record("2-magnetic-cta", async (page) => {
  const cta = page.getByRole("link", { name: "Explore SLO" });
  await cta.scrollIntoViewIfNeeded();
  await sleep(400);
  const box = await cta.boundingBox();
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  for (const [dx, dy] of [
    [40, 0], [0, -18], [-40, 0], [0, 18], [30, 12], [-30, -12], [0, 0],
  ]) {
    await page.mouse.move(cx + dx, cy + dy, { steps: 12 });
    await sleep(260);
  }
  await page.mouse.move(cx + 160, cy + 120, { steps: 16 });
});

await record("3-product-frame-parallax", async (page) => {
  const frame = page.locator(".tilt-surface").first();
  await frame.scrollIntoViewIfNeeded();
  await sleep(400);
  const box = await frame.boundingBox();
  const { x, y, width, height } = box;
  for (const [fx, fy] of [
    [0.1, 0.2], [0.9, 0.2], [0.9, 0.8], [0.1, 0.8], [0.5, 0.5], [0.75, 0.35],
  ]) {
    await page.mouse.move(x + width * fx, y + height * fy, { steps: 20 });
    await sleep(300);
  }
  await page.mouse.move(x - 80, y - 60, { steps: 14 });
});

await record("4-slo-waveform-response", async (page) => {
  await page.goto(`${BASE}/products/smart-sample-manager`, { waitUntil: "networkidle" });
  const wave = page.locator("text=DSP SIGNAL CLASSIFIER").first();
  await wave.scrollIntoViewIfNeeded();
  await sleep(400);
  await page.getByRole("button", { name: "audio_219.wav" }).click();
  await sleep(1200);
  const panel = page.locator("div.relative.h-32").first();
  const box = await panel.boundingBox();
  for (const fx of [0.1, 0.35, 0.6, 0.85, 0.5]) {
    await page.mouse.move(box.x + box.width * fx, box.y + box.height * 0.5, { steps: 14 });
    await sleep(240);
  }
});

await record("5-signal-flow-storytelling", async (page) => {
  await sleep(300);
  const workflow = page.locator(".workflow-list");
  await workflow.scrollIntoViewIfNeeded();
  await sleep(400);
  await page.evaluate(async () => {
    const start = window.scrollY;
    const target = start + 700;
    for (let y = start; y <= target; y += 12) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 24));
    }
  });
  await sleep(600);
});

await browser.close();
console.log("done");
