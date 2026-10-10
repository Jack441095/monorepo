"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

function CheckoutReturnNoticeContent() {
  const searchParams = useSearchParams();
  if (searchParams.get("checkout") !== "success") return null;

  // Stripe's test-session prefix is display-only; a URL can never authorize a production licence.
  const sessionId = searchParams.get("session_id") ?? "";
  const isTestSession = sessionId.startsWith("cs_test_");

  return (
    <section className="site-container mt-6" aria-label="Checkout status">
      <div className="callout-warning" role="status">
        {isTestSession ? (
          <p className="text-sm">
            Stripe test checkout returned successfully. No real money was charged, and a test
            session does not create a production licence.
          </p>
        ) : (
          <p className="text-sm">
            Stripe returned you from checkout. We confirm payments on the server before issuing a
            licence. <Link href="/account?purchase=pending" className="underline font-semibold">Check your account</Link> for the verified purchase.
          </p>
        )}
      </div>
    </section>
  );
}

export function CheckoutReturnNotice() {
  return (
    <Suspense fallback={null}>
      <CheckoutReturnNoticeContent />
    </Suspense>
  );
}
