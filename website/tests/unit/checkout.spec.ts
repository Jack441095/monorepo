import { expect, test } from "@playwright/test";
import { startCheckout } from "../../lib/checkout";

const originalFetch = globalThis.fetch;
const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");

test.beforeEach(() => {
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { location: { origin: "https://nite.example", href: "https://nite.example/pricing" } },
  });
});
test.afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalWindow) Object.defineProperty(globalThis, "window", originalWindow);
  else Reflect.deleteProperty(globalThis, "window");
});

for (const url of ["https://checkout.stripe.com/c/pay/test", "https://buy.stripe.com/test"]) {
  test(`redirects to hosted Stripe checkout: ${url}`, async () => {
    globalThis.fetch = async (_input, init) => {
      expect(JSON.parse(String(init?.body))).toEqual({ price: "intro" });
      return Response.json({ checkout_url: url });
    };
    expect(await startCheckout("intro")).toEqual({ ok: true });
    expect(window.location.href).toBe(url);
  });
}

for (const url of ["http://checkout.stripe.com/test", "https://evilstripe.com/test", "https://checkout.stripe.com.evil.example/test", "javascript:alert(1)", "/checkout"]) {
  test(`rejects an unsafe checkout redirect: ${url}`, async () => {
    globalThis.fetch = async () => Response.json({ checkout_url: url });
    expect((await startCheckout()).ok).toBe(false);
    expect(window.location.href).toBe("https://nite.example/pricing");
  });
}
