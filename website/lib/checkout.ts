import { apiFetch } from "@/lib/api";

// Session-only, cleared the moment it's consumed — carries "the user
// clicked Buy while signed out" across the sign-in redirect. Not used for
// anything else; never touches payment/entitlement state itself, which
// stays server/webhook-authoritative (see docs/PADDLE_INTEGRATION_AUDIT.md).
const BUY_INTENT_KEY = "nitedsp_buy_intent";

export function setBuyIntent() {
  if (typeof window !== "undefined") window.localStorage.setItem(BUY_INTENT_KEY, "1");
}

export function consumeBuyIntent(): boolean {
  if (typeof window === "undefined") return false;
  const had = window.localStorage.getItem(BUY_INTENT_KEY) === "1";
  window.localStorage.removeItem(BUY_INTENT_KEY);
  return had;
}

export type CheckoutPrice = "active" | "intro" | "regular";

export type StartCheckoutResult = { ok: true } | { ok: false; status: number; error: string };

// Calls the existing backend checkout endpoint and navigates to the real
// Paddle-returned URL — the server resolves `price` to an actual Paddle
// price ID; this function never sees or sends one itself (see
// commerce.py's CheckoutRequest / docs/PADDLE_INTEGRATION_AUDIT.md).
export async function startCheckout(price: CheckoutPrice = "active"): Promise<StartCheckoutResult> {
  const res = await apiFetch("/commerce/checkout", {
    method: "POST",
    body: JSON.stringify({ price }),
  });

  if (!res.ok) {
    let detail = "Could not start checkout. Please try again.";
    if (res.status === 401) detail = "Please sign in to continue.";
    else if (res.status === 503) detail = "Checkout isn't available yet.";
    else {
      const body = await res.json().catch(() => null);
      if (body?.detail) detail = String(body.detail);
    }
    return { ok: false, status: res.status, error: detail };
  }

  const data = await res.json();
  const checkoutUrl = typeof data?.checkout_url === "string" ? data.checkout_url : "";
  let parsed: URL;
  try {
    parsed = new URL(checkoutUrl, window.location.origin);
  } catch {
    return { ok: false, status: res.status, error: "Could not start checkout. Please try again." };
  }
  // Defense in depth: the backend supplies a Paddle https URL. Never
  // navigate to a non-https or non-Paddle URL even if the response is
  // compromised or a dev backend misbehaves.
  if (parsed.protocol !== "https:" || !parsed.hostname.endsWith("paddle.com")) {
    return { ok: false, status: res.status, error: "Could not start checkout. Please try again." };
  }
  window.location.href = parsed.toString();
  return { ok: true };
}
