import { expect, test } from "@playwright/test";

/* Regression cover for the pre-launch SEO audit.
 *
 * What broke before, and is guarded here:
 *  - /products rendered "Product Families | NITE DSP | NITE DSP" (its title
 *    already carried the suffix the root template appends).
 *  - The homepage and all four legal pages shared one inherited title
 *    ("NITE DSP") and description, with no canonical at all.
 *  - Every page inherited the root layout's og:url, so every share card
 *    pointed at the homepage. lib/seo.ts now derives canonical and og:url
 *    from one `path`.
 *  - /products/slo (a redirect) was listed in the sitemap while the real
 *    /technology and /products/files pages were missing from it.
 */

const INDEXABLE_ROUTES = [
  "/",
  "/products",
  "/products/submit",
  "/products/smart-sample-manager",
  "/products/kenn",
  "/products/files",
  "/technology",
  "/thursday",
  "/trust",
  "/pricing",
  "/support",
  "/learn",
  "/download",
  "/beta",
  "/privacy",
  "/terms",
  "/eula",
  "/refund-policy",
];

test("every indexable page has a unique, non-default title and description", async ({ page }) => {
  const seenTitles = new Map<string, string>();
  const seenDescriptions = new Map<string, string>();

  for (const route of INDEXABLE_ROUTES) {
    await page.goto(route);
    const title = await page.title();
    const description = await page
      .locator('meta[name="description"]')
      .getAttribute("content");

    expect(title, `${route} has a title`).toBeTruthy();
    expect(description, `${route} has a description`).toBeTruthy();

    // The bare layout default must never surface as a page's own title.
    expect(title, `${route} still shows the inherited default title`).not.toBe("NITE DSP");
    // "X | NITE DSP | NITE DSP" — the doubled-suffix bug. A title may
    // legitimately contain the brand (e.g. "Thursday: The NITE DSP
    // Intelligence Layer | NITE DSP"); only the repeated suffix is wrong.
    expect(title, `${route} doubles the title suffix`).not.toMatch(/\| NITE DSP \| NITE DSP$/);

    const titleOwner = seenTitles.get(title);
    expect(titleOwner, `${route} duplicates the title of ${titleOwner}`).toBeUndefined();
    seenTitles.set(title, route);

    const descOwner = seenDescriptions.get(description!);
    expect(descOwner, `${route} duplicates the description of ${descOwner}`).toBeUndefined();
    seenDescriptions.set(description!, route);
  }
});

test("canonical and og:url agree and point at the page itself", async ({ page }) => {
  for (const route of INDEXABLE_ROUTES) {
    await page.goto(route);
    const canonical = await page.locator('link[rel="canonical"]').getAttribute("href");
    const ogUrl = await page.locator('meta[property="og:url"]').getAttribute("content");

    expect(canonical, `${route} is missing a canonical`).toBeTruthy();
    expect(new URL(canonical!).pathname.replace(/\/$/, "")).toBe(route.replace(/\/$/, ""));
    // og:url used to be the homepage on every single page.
    expect(new URL(ogUrl!).pathname.replace(/\/$/, ""), `${route} og:url does not match its canonical`)
      .toBe(route.replace(/\/$/, ""));
  }
});

test("session-gated routes are noindex at the page level, not just in robots.txt", async ({ page }) => {
  for (const route of ["/account", "/auth/verify"]) {
    await page.goto(route);
    const robots = await page.locator('meta[name="robots"]').getAttribute("content");
    expect(robots, `${route} should be noindex`).toContain("noindex");
  }
});

test("sitemap lists real pages and no redirects", async ({ request }) => {
  const xml = await (await request.get("/sitemap.xml")).text();

  for (const route of ["/technology", "/products/files"]) {
    expect(xml, `sitemap is missing ${route}`).toContain(`<loc>https://www.nitedsp.co.uk${route}</loc>`);
  }
  // /products/slo only ever redirects to /products/smart-sample-manager.
  expect(xml).not.toContain("<loc>https://www.nitedsp.co.uk/products/slo</loc>");
  // Unlisted, password-gated, robots-disallowed.
  expect(xml).not.toContain("/portfolio");
});

test("browser-tab presentation is configured", async ({ page, request }) => {
  await page.goto("/");
  await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute("content", "#090B10");
  await expect(page.locator('link[rel="manifest"]')).toHaveCount(1);

  const manifest = await (await request.get("/manifest.webmanifest")).json();
  expect(manifest.name).toBe("NITE DSP");
  expect(manifest.theme_color).toBe("#090B10");
  expect(manifest.icons.length).toBeGreaterThan(0);
});

test("product pages carry their own share image, not the site default", async ({ page, request }) => {
  // Every page used to inherit the root card, which read "SLO / Sample
  // Library Optimiser" -- so sharing the homepage or Submit advertised SLO.
  await page.goto("/");
  const rootImage = await page.locator('meta[property="og:image"]').getAttribute("content");
  expect(rootImage).toBeTruthy();

  const seen = new Set([new URL(rootImage!).pathname]);
  for (const route of [
    "/products/smart-sample-manager",
    "/products/submit",
    "/products/kenn",
    "/products/files",
  ]) {
    await page.goto(route);
    const image = await page.locator('meta[property="og:image"]').getAttribute("content");
    expect(image, `${route} has no og:image`).toBeTruthy();

    const path = new URL(image!).pathname;
    expect(path, `${route} falls back to the site-default share image`).not.toBe(
      new URL(rootImage!).pathname,
    );
    expect(seen.has(path), `${route} reuses another page's share image`).toBe(false);
    seen.add(path);

    // And it has to actually render.
    const res = await request.get(image!.replace(/^https:\/\/www\.nitedsp\.co\.uk/, ""));
    expect(res.status(), `${route} share image does not render`).toBe(200);
    expect(res.headers()["content-type"]).toContain("image/png");
  }
});

test("sitemap does not claim every page changed on this build", async ({ request }) => {
  // lastModified was `new Date()`, stamping the build time onto every URL.
  const xml = await (await request.get("/sitemap.xml")).text();
  expect(xml).not.toContain("<lastmod>");
});
