"use client";

import { useEffect, useState } from "react";

const PADDLE_CLIENT_TOKEN = process.env.NEXT_PUBLIC_PADDLE_CLIENT_TOKEN;
const PADDLE_ENV = process.env.NEXT_PUBLIC_PADDLE_ENV;

/**
 * Initializes Paddle.js once on the pricing page so that when the browser
 * lands here with Paddle's `_ptxn` query param (the redirect target of
 * POST /commerce/checkout's returned checkout_url), Paddle.js auto-opens
 * the checkout overlay for that transaction on its own -- no manual
 * `_ptxn` handling needed, per Paddle's documented default-payment-link
 * behavior. Renders nothing by itself; CtaButton owns the actual Buy button.
 */
export function PaddleCheckoutOverlay() {
  const [error, setError] = useState<string | null>(null);

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

  if (!error) return null;
  return (
    <p className="mt-3 text-xs" style={{ color: "var(--state-error)" }} role="alert">
      {error}
    </p>
  );
}
