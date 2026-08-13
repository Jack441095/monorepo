import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Pricing",
  description: "Smart Sample Manager pricing -- one-time purchase, perpetual license.",
  alternates: { canonical: "/pricing" },
};

export default function PricingPage() {
  return (
    <div className="section">
      <div className="mx-auto px-6 text-center" style={{ maxWidth: "40rem" }}>
        <span className="eyebrow">Pricing</span>
        <h1 className="mt-3 text-3xl sm:text-4xl font-semibold tracking-tight">
          One price. Yours to keep.
        </h1>
        <p className="mt-4" style={{ color: "var(--muted)" }}>
          A single purchase, a perpetual license, free updates within the version. No subscription.
        </p>

        <div className="mt-10 surface-card p-8 mx-auto" style={{ maxWidth: "26rem" }}>
          <span className="badge-experimental" style={{ borderColor: "var(--border-strong)", color: "var(--muted)" }}>
            Introductory launch price
          </span>
          <h2 className="mt-3 text-lg font-medium">Smart Sample Manager</h2>
          <div className="mt-4 flex items-baseline justify-center gap-2">
            <span className="text-4xl font-semibold">£5</span>
            <span className="text-sm" style={{ color: "var(--muted-dim)" }}>one-time</span>
          </div>
          <p className="mt-1 text-xs" style={{ color: "var(--muted-dim)" }}>
            £10 one-time after the introductory launch period.
          </p>

          <ul className="mt-6 space-y-2 text-sm text-left" style={{ color: "var(--muted)" }}>
            <li>Perpetual license -- yours after one purchase</li>
            <li>No subscription, ever</li>
            <li>Up to 3 active machine activations</li>
            <li>macOS -- VST3, AU, Standalone</li>
            <li>Free updates within the 1.x version line</li>
          </ul>

          <Link href="/account" className="btn-primary mt-6 w-full">
            Sign in
          </Link>
          <p className="mt-4 text-xs" style={{ color: "var(--muted-dim)" }}>
            Checkout is not yet live -- real checkout requires a live Merchant of Record account,
            which does not exist yet.
          </p>
        </div>

        <p className="mt-6 text-xs" style={{ color: "var(--muted-dim)" }}>
          A 14-day full-featured trial is planned but not yet available.
        </p>
      </div>
    </div>
  );
}
