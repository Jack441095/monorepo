"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { setBuyIntent, startCheckout } from "@/lib/checkout";

const PADDLE_CLIENT_TOKEN = process.env.NEXT_PUBLIC_PADDLE_CLIENT_TOKEN;
const PADDLE_ENV = process.env.NEXT_PUBLIC_PADDLE_ENV;

export function BuyCard() {
  const router = useRouter();
  const [buyState, setBuyState] = useState<"idle" | "checking" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  // Initialize Paddle.js once, so that if this page loads with Paddle's
  // `_ptxn` query param present (the redirect target of a checkout URL
  // POST /commerce/checkout just returned), Paddle.js auto-opens the
  // checkout for that transaction on its own — no manual detection code
  // needed, per Paddle's documented default-payment-link behavior. This
  // effect does nothing if the client token isn't configured yet.
  useEffect(() => {
    if (!PADDLE_CLIENT_TOKEN || !PADDLE_ENV) return;
    let cancelled = false;
    import("@paddle/paddle-js").then(({ initializePaddle }) => {
      if (cancelled) return;
      initializePaddle({
        token: PADDLE_CLIENT_TOKEN,
        environment: PADDLE_ENV as "sandbox" | "production",
        checkout: {
          settings: {
            successUrl: "/account?purchase=pending",
          },
        },
        eventCallback: (event) => {
          if (event.name === "checkout.error") {
            setError("Something went wrong opening checkout. Please try again or contact support.");
          }
        },
      });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleBuy() {
    setBuyState("checking");
    setError(null);

    let meRes: Response;
    try {
      meRes = await apiFetch("/auth/me");
    } catch {
      // An unavailable auth endpoint must not leave a prospective buyer on
      // the pricing page with a disabled button and no next step.
      setBuyIntent();
      router.push("/account");
      return;
    }
    if (!meRes.ok) {
      setBuyIntent();
      router.push("/account");
      return;
    }

    const result = await startCheckout("active");
    if (!result.ok) {
      setBuyState("error");
      setError(result.error);
      return;
    }
    // On success, startCheckout() has already navigated the page away.
  }

  const paddleConfigured = Boolean(PADDLE_CLIENT_TOKEN && PADDLE_ENV);

  return (
    <>
      {paddleConfigured ? (
        <button
          onClick={handleBuy}
          disabled={buyState === "checking"}
          className="btn-primary mt-6 w-full"
        >
          {buyState === "checking" ? "Starting checkout…" : "Test Checkout (Sandbox)"}
        </button>
      ) : (
        <Link href="/account" className="btn-primary mt-6 w-full">
          Register Interest (Sign In)
        </Link>
      )}

      {error && (
        <p className="mt-3 text-xs" style={{ color: "var(--state-error)" }} role="alert">
          {error}
        </p>
      )}

      {paddleConfigured ? (
        <p className="mt-4 text-xs" style={{ color: "var(--muted-dim)" }}>
          Sandbox / test mode — simulated checkout for integration testing. No real funds are charged.
        </p>
      ) : (
        <p className="mt-4 text-xs" style={{ color: "var(--muted-dim)" }}>
          Private beta is currently in preparation. Pricing will be finalized and purchases enabled upon launch.
        </p>
      )}
    </>
  );
}
