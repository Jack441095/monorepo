import { expect, test, type Page } from "@playwright/test";

/* Regression cover for the pre-launch visual/accessibility audit.
 *
 * Two defect classes are guarded here, both found across the whole site:
 *  - Horizontal overflow at 320px. /products/kenn scrolled sideways because
 *    the product frame sits in a grid track (min-width:auto by default) and
 *    its title bar carried 2.5rem of side padding — 80px on a 320px screen.
 *  - Text contrast below WCAG AA. --muted-dim, the .btn-primary fill and
 *    --brand-violet-as-text all failed 4.5:1; 189 failing nodes in total.
 *
 * Contrast is computed here rather than pulled from axe so the suite stays
 * dependency-free.
 */

const ROUTES = [
  "/",
  "/products",
  "/products/kenn",
  "/products/files",
  "/products/smart-sample-manager",
  "/pricing",
  "/learn",
  "/technology",
  "/privacy",
];

const NARROW_WIDTHS = [320, 375, 768];

test.describe("no horizontal overflow on small screens", () => {
  for (const width of NARROW_WIDTHS) {
    test(`viewport ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      for (const route of ROUTES) {
        await page.goto(route);
        const { scrollWidth, clientWidth } = await page.evaluate(() => ({
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        }));
        // 1px of slack for subpixel rounding.
        expect(scrollWidth, `${route} scrolls horizontally at ${width}px`)
          .toBeLessThanOrEqual(clientWidth + 1);
      }
    });
  }
});

/** Every rendered text node's contrast against its effective background. */
async function findLowContrastText(page: Page) {
  return page.evaluate(() => {
    // Tailwind v4 emits oklab()/lab() colours, so computed values cannot be
    // parsed as plain rgb() triples. Painting each colour onto a 1x1 canvas
    // makes the browser do the conversion and hands back real sRGB bytes.
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 1;
    const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
    const cache = new Map<string, number[]>();

    const toRgba = (color: string): number[] => {
      const hit = cache.get(color);
      if (hit) return hit;
      ctx.clearRect(0, 0, 1, 1);
      ctx.fillStyle = "#000";
      ctx.fillStyle = color;
      ctx.globalCompositeOperation = "copy";
      ctx.fillRect(0, 0, 1, 1);
      const d = ctx.getImageData(0, 0, 1, 1).data;
      const out = [d[0], d[1], d[2], d[3] / 255];
      cache.set(color, out);
      return out;
    };

    const luminance = (rgb: number[]) => {
      const [r, g, b] = rgb.map((v) => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };

    /** Walks up compositing every layer down to the first opaque one. */
    const backgroundOf = (el: Element): number[] => {
      const layers: number[][] = [];
      let node: Element | null = el;
      while (node) {
        const [r, g, b, a] = toRgba(getComputedStyle(node).backgroundColor);
        if (a > 0) {
          layers.push([r, g, b, a]);
          if (a === 1) break;
        }
        node = node.parentElement;
      }
      // Nothing opaque found: assume the canvas default.
      let out = [255, 255, 255];
      for (let i = layers.length - 1; i >= 0; i--) {
        const [r, g, b, a] = layers[i];
        out = [r * a + out[0] * (1 - a), g * a + out[1] * (1 - a), b * a + out[2] * (1 - a)];
      }
      return out;
    };

    const failures: string[] = [];
    for (const el of Array.from(document.querySelectorAll("*"))) {
      // Only leaf elements that render their own visible text.
      if (el.children.length > 0) continue;
      const text = el.textContent?.trim();
      if (!text) continue;
      const style = getComputedStyle(el);
      if (style.visibility === "hidden" || style.display === "none") continue;
      if (parseFloat(style.opacity) === 0) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;

      const [fr, fg_, fb, fa] = toRgba(style.color);
      if (fa === 0) continue;
      const bg = backgroundOf(el);
      const blended = [
        fr * fa + bg[0] * (1 - fa),
        fg_ * fa + bg[1] * (1 - fa),
        fb * fa + bg[2] * (1 - fa),
      ];

      const l1 = luminance(blended);
      const l2 = luminance(bg);
      const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);

      // WCAG AA: 3:1 for large text (>=24px, or >=18.66px bold), else 4.5:1.
      const size = parseFloat(style.fontSize);
      const bold = parseInt(style.fontWeight, 10) >= 700;
      const required = size >= 24 || (bold && size >= 18.66) ? 3 : 4.5;

      if (ratio < required) {
        failures.push(
          `${ratio.toFixed(2)}:1 (needs ${required}) "${text.slice(0, 40)}" <${el.tagName.toLowerCase()} class="${String(el.className).slice(0, 70)}">`,
        );
      }
    }
    return failures;
  });
}

test.describe("text meets WCAG AA contrast", () => {
  for (const route of ROUTES) {
    test(`${route}`, async ({ page }) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(route);
      const failures = await findLowContrastText(page);
      expect(failures, `low-contrast text on ${route}:\n${failures.join("\n")}`).toEqual([]);
    });
  }
});

test("mobile menu closes on Escape and returns focus to its toggle", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/");

  const toggle = page.getByRole("button", { name: "Open menu" });
  await toggle.click();
  await expect(page.locator("#mobile-nav")).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(page.locator("#mobile-nav")).toBeHidden();
  await expect(page.getByRole("button", { name: "Open menu" })).toBeFocused();
});

test("header shows one account affordance per breakpoint", async ({ page }) => {
  // .btn-secondary sets display from unlayered CSS and outranked Tailwind's
  // `hidden`, so the desktop Account button used to render on phones too --
  // beside the hamburger, and a second time inside the open menu.
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/");
  await expect(page.locator("header").getByRole("link", { name: "Account" })).toBeHidden();
  await expect(page.getByRole("button", { name: "Open menu" })).toBeVisible();

  await page.getByRole("button", { name: "Open menu" }).click();
  await expect(page.locator("#mobile-nav").getByRole("link", { name: "Account" })).toBeVisible();

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/");
  await expect(page.locator("header").getByRole("link", { name: "Account" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open menu" })).toBeHidden();
});

test("size utilities written beside .btn-* actually apply", async ({ page }) => {
  // .btn-primary/.btn-secondary live in @layer components so Tailwind's
  // utilities outrank them. Unlayered, the component font-size and padding
  // won, and every compact variant (the demo toolbars' `text-[11px] px-3
  // py-1.5`) silently rendered at the full 14px / 44px-tall size.
  await page.goto("/products/smart-sample-manager");
  const reset = page.getByRole("button", { name: "Reset demo" }).first();
  await reset.scrollIntoViewIfNeeded();

  const box = await reset.evaluate((el) => {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return { fontSize: cs.fontSize, height: Math.round(r.height), width: Math.round(r.width) };
  });

  expect(box.fontSize).toBe("11px");
  expect(box.height).toBeLessThan(40);
  // WCAG 2.2 AA target size minimum is 24x24 CSS px, so compact must not
  // become unhittable.
  expect(box.height).toBeGreaterThanOrEqual(24);
  expect(box.width).toBeGreaterThanOrEqual(24);
});

test("SLO map dots meet WCAG 2.2 target size and spacing", async ({ page }) => {
  // The dots are 10-14px visually. They now sit inside 28px hit areas, and
  // two pairs of demo coordinates had to move apart so those areas stop
  // overlapping at mobile width (WCAG 2.2 AA 2.5.8 covers size AND spacing).
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto("/products/smart-sample-manager");

  const dots = page.locator('button[aria-label^="Select sample"]');
  await dots.first().scrollIntoViewIfNeeded();
  expect(await dots.count()).toBeGreaterThan(1);

  const boxes = await dots.evaluateAll((els) =>
    els.map((el) => {
      const r = el.getBoundingClientRect();
      return { cx: r.left + r.width / 2, cy: r.top + r.height / 2, w: r.width, h: r.height };
    }),
  );

  for (const b of boxes) {
    expect(b.w).toBeGreaterThanOrEqual(24);
    expect(b.h).toBeGreaterThanOrEqual(24);
  }

  // No two hit areas may overlap.
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const distance = Math.hypot(boxes[i].cx - boxes[j].cx, boxes[i].cy - boxes[j].cy);
      expect(distance, `map dots ${i} and ${j} overlap (${distance.toFixed(1)}px apart)`)
        .toBeGreaterThanOrEqual(24);
    }
  }
});
