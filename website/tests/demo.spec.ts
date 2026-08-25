import { expect, test } from "@playwright/test";

/* Interactive Demonstration Layer V1 — regression coverage.
   Contracts only: demos load, honesty labels persist, keyboard works,
   mobile does not overflow, reduced motion still reaches results, and the
   console stays clean. Never exact animation coordinates. */

test.describe("interactive demonstration layer", () => {
  test("homepage signal journey renders all four stages", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("The NITE Signal Journey")).toBeVisible();
    for (const stage of ["DISCOVER", "ANALYSE", "UNDERSTAND", "CREATE"]) {
      await expect(page.getByText(stage, { exact: true })).toBeVisible();
    }
  });

  test("SLO demo resolves with acoustic matches and keeps its labels", async ({ page }) => {
    await page.goto("/");
    const demo = page.getByRole("region", { name: /SLO sample analysis demonstration/ });
    await demo.scrollIntoViewIfNeeded();
    await demo.getByRole("button", { name: "XK29_0047.wav" }).click();
    await expect(demo.getByText("KICK", { exact: true })).toBeVisible({ timeout: 5000 });
    await expect(demo.getByText("SIMILARITY — ACOUSTIC MATCHES")).toBeVisible();
    await expect(demo.getByText("Kick_012.wav")).toBeVisible();
    await expect(demo.getByText("SPECTRAL CENTROID", { exact: true })).toBeVisible();
    await expect(demo.getByText("82 Hz", { exact: true })).toBeVisible();
    await expect(demo.getByText("SIMULATION", { exact: true })).toBeVisible();
    await expect(demo.getByText(/Illustrative workflow simulation/i)).toBeVisible();
  });

  test("SLO demo reset returns to idle", async ({ page }) => {
    await page.goto("/");
    const demo = page.getByRole("region", { name: /SLO sample analysis demonstration/ });
    await demo.scrollIntoViewIfNeeded();
    await demo.getByRole("button", { name: "audio_219.wav" }).click();
    await expect(demo.getByText("SYNTH PAD", { exact: true })).toBeVisible({ timeout: 5000 });
    await demo.getByRole("button", { name: "Reset" }).click();
    await expect(demo.getByText("Select a sample to begin")).toBeVisible();
    await expect(demo.getByText("RESULT READY")).toBeHidden();
  });

  test("Submit simulation runs to preparation result with honest framing", async ({ page }) => {
    await page.goto("/products");
    const demo = page.getByRole("region", { name: /Submit document preparation console demonstration/ });
    await demo.scrollIntoViewIfNeeded();
    await demo.getByRole("button", { name: /Assignment_Final\.pdf/ }).click();
    await expect(demo.getByText("PREPARED", { exact: true })).toBeVisible({ timeout: 5000 });
    await expect(demo.getByText("Remove redundant 'Final' tag from filename")).toBeVisible();
    await expect(demo.getByText("SIMULATION", { exact: true })).toBeVisible();
    await expect(demo.getByText("LOCAL CHECK ONLY", { exact: true })).toBeVisible();
    await expect(demo.getByText("0 BYTES UPLOADED", { exact: true })).toBeVisible();
    await expect(demo.getByText(/never submits automatically/i)).toBeVisible();
  });

  test("Submit simulation flags a second document differently", async ({ page }) => {
    await page.goto("/products");
    const demo = page.getByRole("region", { name: /Submit document preparation console demonstration/ });
    await demo.scrollIntoViewIfNeeded();
    await demo.getByRole("button", { name: /Thesis_Chapter2\.docx/ }).click();
    // This demo runs the same 1.9s scan/analysis state machine as the other
    // fixtures; allow extra headroom when the full Chromium suite is under
    // parallel worker load on Rosetta.
    await expect(demo.getByText("Student name header missing")).toBeVisible({ timeout: 10000 });
    await expect(demo.getByText("Resolve name header before export")).toBeVisible();
  });

  test("KENN concept demo produces explainable suggestions", async ({ page }) => {
    await page.goto("/products");
    const demo = page.getByRole("region", { name: /KENN mix analysis concept demonstration/ });
    await demo.scrollIntoViewIfNeeded();
    await demo.getByRole("button", { name: /Run mix review/i }).click();
    await expect(demo.getByText("REVIEW RECOMMENDED", { exact: true })).toBeVisible({ timeout: 5000 });
    await expect(demo.getByText("Apply a 24dB/oct high-pass filter at 30Hz or reduce low shelf by 1.8dB")).toBeVisible();
    await expect(demo.getByText("EXPLAINABLE SUGGESTION", { exact: true })).toBeVisible();
    await expect(demo.getByText("CONCEPT DEMO", { exact: true })).toBeVisible();
    await expect(demo.getByText(/offers evidence-based observations/i)).toBeVisible();
  });

  test("demos are keyboard operable", async ({ page }) => {
    await page.goto("/products");
    const demo = page.getByRole("region", { name: /Submit document preparation console demonstration/ });
    await demo.scrollIntoViewIfNeeded();
    await demo.getByRole("button", { name: /Assignment_Final\.pdf/ }).focus();
    await page.keyboard.press("Enter");
    await expect(demo.getByText("PREPARED", { exact: true })).toBeVisible({ timeout: 5000 });
  });

  test("reduced motion: demos still reach their results", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/products");
    const kenn = page.getByRole("region", { name: /KENN mix analysis concept demonstration/ });
    await kenn.scrollIntoViewIfNeeded();
    await kenn.getByRole("button", { name: /Run mix review/i }).click();
    await expect(kenn.getByText("REVIEW RECOMMENDED", { exact: true })).toBeVisible({ timeout: 5000 });

    const submit = page.getByRole("region", { name: /Submit document preparation console demonstration/ });
    await submit.scrollIntoViewIfNeeded();
    await submit.getByRole("button", { name: /Assignment_Final\.pdf/ }).click();
    await expect(submit.getByText("PREPARED", { exact: true })).toBeVisible({ timeout: 5000 });
  });

  test("demos introduce no horizontal overflow on mobile", async ({ browser }) => {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      hasTouch: true,
      isMobile: true,
    });
    const page = await context.newPage();
    for (const route of ["/", "/products"]) {
      await page.goto(route);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `horizontal overflow on ${route}`).toBeLessThanOrEqual(1);
    }
    await context.close();
  });

  test("demo routes load without console or page errors", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    page.on("pageerror", (err) => errors.push(String(err)));
    for (const route of ["/", "/products", "/products/smart-sample-manager"]) {
      await page.goto(route);
      await page.waitForTimeout(400);
    }
    expect(errors).toEqual([]);
  });
});
