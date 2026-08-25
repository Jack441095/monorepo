"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Magnetic } from "@/components/motion/Magnetic";
import { CHECKOUT_LIVE } from "@/lib/commerce-config";
import { setBuyIntent, startCheckout } from "@/lib/checkout";

/**
 * Single CTA state machine for every commercial surface (see
 * docs/NITE_DSP_CONVERSION_COMMERCIAL_UX_V1.md §1).
 *
 * States map 1:1 to commercial maturity — the label always states what
 * happens next, so a closed checkout never presents a dead Buy button:
 *   BUY_LIVE      checkout enabled  → server-resolved Paddle checkout
 *   BETA_REQUEST  closed beta       → /beta request journey
 *   NOTIFY_ME     pre-beta product  → /beta (notify list)
 */
export type CtaState = "BUY_LIVE" | "BETA_REQUEST" | "NOTIFY_ME";

export function CtaButton({
  state,
  label,
  secondary = false,
}: {
  state: CtaState;
  /** Override label; defaults are claims-safe per the copy register. */
  label?: string;
  secondary?: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Launch switch: BUY_LIVE renders the buy flow only when checkout is
  // actually open; otherwise it degrades to the honest beta-request CTA.
  const effectiveState: CtaState =
    state === "BUY_LIVE" && !CHECKOUT_LIVE ? "BETA_REQUEST" : state;

  if (effectiveState === "BUY_LIVE") {
    async function buy() {
      setBusy(true);
      setError(null);
      const result = await startCheckout("active");
      if (!result.ok) {
        // 401: persist intent across the sign-in redirect (existing pattern
        // from pricing/BuyCard). Anything else surfaces honestly.
        if (result.status === 401) {
          setBuyIntent();
          router.push("/account");
          return;
        }
        setError(result.error);
        setBusy(false);
      }
      // Success: startCheckout has navigated away already.
    }
    return (
      <span className="inline-flex flex-col items-start gap-2">
        <button
          type="button"
          className={secondary ? "btn-secondary" : "btn-primary"}
          onClick={buy}
          disabled={busy}
        >
          <Magnetic>{busy ? "Opening checkout…" : (label ?? "Buy now")}</Magnetic>
        </button>
        {error && (
          <span role="alert" className="text-xs" style={{ color: "var(--state-error)" }}>
            {error}{" "}
            <Link href="/support" className="text-link">
              Contact support
            </Link>
          </span>
        )}
      </span>
    );
  }

  if (effectiveState === "BETA_REQUEST") {
    return (
      <Link href="/beta" className={secondary ? "btn-secondary" : "btn-primary"}>
        <Magnetic>{label ?? "Request beta access"}</Magnetic>
      </Link>
    );
  }

  // NOTIFY_ME
  return (
    <Link href="/beta?intent=notify" className={secondary ? "btn-secondary" : "btn-primary"}>
      <Magnetic>{label ?? "Notify me"}</Magnetic>
    </Link>
  );
}
